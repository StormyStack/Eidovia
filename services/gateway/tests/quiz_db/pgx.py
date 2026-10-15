"""
Test harness: runs the REAL gateway/admin SQL against a REAL PostgreSQL 16 server, one psql process per
session (= one connection, one transaction), behaving like SQLAlchemy text() + asyncpg:

  * bind parameters are found with SQLAlchemy's own text() regex; a missing value is an error, "\\:" is a literal colon
  * every statement with parameters is PREPAREd, so PostgreSQL infers the parameter types exactly like asyncpg
    (e.g. "operator is not unique: unknown + unknown" fails here too)
  * each Python value is checked against the inferred type the way asyncpg's codecs do (str for an INT fails, ...)
  * results are converted by their PostgreSQL types (int, Decimal, datetime, UUID, jsonb -> Python objects, arrays)
  * get_session(commit=True) commits on success (gateway); commit=False never commits by itself (admin app)

Concurrency is real: two sessions in two threads are two connections, so row locks, advisory locks and unique
indexes behave as in production.
"""

import contextlib
import datetime as dt
import decimal
import itertools
import json
import os
import re
import subprocess
import threading
import uuid

PGHOST, PGPORT = os.environ.get("PGX_HOST", "/tmp"), os.environ.get("PGX_PORT", "5433")
DBNAME = os.environ.get("PGX_DB", "quizt")
BIND = re.compile(r"(?<![:\w\x5c]):(\w+)(?!:)")       # sqlalchemy.sql.elements.TextClause._bind_params_regex
FS, RS = "\x1f", "\x1e"
NULL = "\x01N"
_ids = itertools.count(1)

INT = {"smallint", "integer", "bigint"}
NUM = {"numeric", "real", "double precision"}
TXT = {"text", "character varying", "character", "name", "unknown"}
TS = {"timestamp with time zone", "timestamp without time zone"}


class SQLError(Exception):
    pass


class DataError(SQLError):
    """Like asyncpg.exceptions.DataError: a Python value that does not fit the inferred parameter type."""


def psql(sql: str, db: str = None) -> str:
    out = subprocess.run(["psql", "-h", PGHOST, "-p", PGPORT, "-U", "postgres", "-d", db or DBNAME, "-X", "-q", "-At",
                          "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True)
    if out.returncode:
        raise SQLError(out.stderr.strip() + "\n" + sql)
    return out.stdout


def reset_db(name: str = None) -> None:
    name = name or DBNAME
    psql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)", "postgres")
    psql(f"CREATE DATABASE {name}", "postgres")


def _check(value, typ: str, i: int) -> None:
    if value is None:
        return
    bad = False
    if typ in INT:
        bad = not isinstance(value, int) or isinstance(value, bool)
    elif typ in NUM:
        bad = not isinstance(value, (int, float, decimal.Decimal)) or isinstance(value, bool)
    elif typ in TXT:
        bad = not isinstance(value, str)
    elif typ == "uuid":
        bad = not isinstance(value, (str, uuid.UUID))
    elif typ in TS:
        bad = not isinstance(value, dt.datetime)
    elif typ == "boolean":
        bad = not isinstance(value, bool)
    elif typ in ("jsonb", "json"):
        bad = not isinstance(value, str)       # SQLAlchemy's asyncpg json codec encodes a str
    elif typ.endswith("[]"):
        bad = not isinstance(value, (list, tuple))
    else:
        raise DataError(f"harness: no rule for parameter type {typ}")
    if bad:
        raise DataError(f"invalid input for query argument ${i}: {value!r} ({type(value).__name__} is not {typ})")


def _quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _literal(value, typ: str) -> str:
    if value is None:
        return f"NULL::{typ}"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, dt.datetime):
        return f"{_quote(value.isoformat())}::{typ}"
    if isinstance(value, (list, tuple)):
        items = ",".join('"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"' if v is not None else "NULL" for v in value)
        return f"{_quote('{' + items + '}')}::{typ}"
    return f"{_quote(str(value))}::{typ}"


def _array(text: str, conv):
    inner = text[1:-1]
    if not inner:
        return []
    return [None if x == "NULL" else conv(x.strip('"')) for x in inner.split(",")]


def _ts(v: str) -> dt.datetime:
    return dt.datetime.fromisoformat(v)


def _convert(v: str, typ: str):
    if v == NULL:
        return None
    if typ in INT:
        return int(v)
    if typ == "numeric":
        return decimal.Decimal(v)
    if typ in ("real", "double precision"):
        return float(v)
    if typ == "boolean":
        return v == "t"
    if typ in TS:
        return _ts(v)
    if typ == "uuid":
        return uuid.UUID(v)
    if typ in ("json", "jsonb"):
        return json.loads(v)
    if typ.endswith("[]"):
        base = typ[:-2]
        return _array(v, lambda x: _convert(x, base))
    return v


class Row:
    def __init__(self, names, values):
        self._names, self._values = names, values
        self._mapping = dict(zip(names, values))

    def __getattr__(self, name):
        try:
            return self.__dict__["_mapping"][name]
        except KeyError:
            raise AttributeError(name)

    def __getitem__(self, i):
        return self._values[i]

    def __iter__(self):
        return iter(self._values)

    def __repr__(self):
        return f"Row({self._mapping})"


class Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0][0] if self._rows else None

    def fetchall(self):
        return self.all()

    def mappings(self):
        return Result([r._mapping for r in self._rows])


class Session:
    """One connection (psql process). Statements run inside one transaction until commit/rollback."""

    def __init__(self):
        self.p = subprocess.Popen(
            ["psql", "-h", PGHOST, "-p", PGPORT, "-U", "postgres", "-d", DBNAME, "-X", "-q", "-A", "-F", FS, "-R", RS,
             "-P", "footer=off", "-P", f"null={NULL}", "-v", "ON_ERROR_STOP=0"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.in_tx = False
        self.failed = False
        self.statements = []
        self._raw("SET client_min_messages = warning")

    def _raw(self, sql: str) -> str:
        marker = f"__END_{next(_ids)}__"
        self.p.stdin.write(sql.rstrip().rstrip(";") + ";\n\\echo " + marker + "\n")
        self.p.stdin.flush()
        out = []
        while True:
            line = self.p.stdout.readline()
            if line == "":
                raise SQLError("psql exited")
            if line.rstrip("\r\n") == marker:
                break
            # the marker may follow output on the same line (records end with RS, not a newline)
            if line.rstrip("\r\n").endswith(marker):
                out.append(line.rstrip("\r\n")[: -len(marker)])
                break
            out.append(line)
        text = "".join(out)
        m = re.search(r"(?m)^(?:psql:[^\n]*?:\d+: )?(ERROR|FATAL):\s+(.*)", text)
        if m:
            self.failed = self.in_tx
            raise SQLError(m.group(2).strip())
        return text

    def _begin(self):
        if not self.in_tx:
            self._raw("BEGIN")
            self.in_tx, self.failed = True, False

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = dict(params or {})
        names = []
        for m in BIND.finditer(sql):
            if m.group(1) not in names:
                names.append(m.group(1))
        missing = [n for n in names if n not in params]
        if missing:
            raise SQLError(f"A value is required for bind parameter {missing[0]!r}")
        pos = {n: i + 1 for i, n in enumerate(names)}
        sql = BIND.sub(lambda m: f"${pos[m.group(1)]}", sql).replace("\\:", ":")
        self._begin()
        if self.failed:
            raise SQLError("current transaction is aborted")
        self.statements.append(sql)
        head = sql.lstrip().split(None, 1)[0].upper()
        if not names and head not in ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "VALUES"):
            self._raw(sql)
            return Result([])
        name = f"q{next(_ids)}"
        try:
            self._raw(f"PREPARE {name} AS {sql}")
        except SQLError:
            raise
        info = self._raw(f"SELECT array_to_string(parameter_types::text[], '|'), "
                         f"coalesce(array_to_string(result_types::text[], '|'), '') "
                         f"FROM pg_prepared_statements WHERE name = '{name}'")
        info = info.strip(RS + "\n").split(RS)[-1]
        ptypes_s, rtypes_s = info.split(FS)
        ptypes = [self._typename(t) for t in ptypes_s.split("|")] if ptypes_s else []
        rtypes = [self._typename(t) for t in rtypes_s.split("|")] if rtypes_s else []
        try:
            values = [params[n] for n in names]
            for i, (v, t) in enumerate(zip(values, ptypes), 1):
                _check(v, t, i)
            args = ", ".join(_literal(v, t) for v, t in zip(values, ptypes))
            out = self._raw(f"EXECUTE {name}" + (f"({args})" if args else ""))
        finally:
            if not self.failed:
                self._raw(f"DEALLOCATE {name}")
        if not rtypes:
            return Result([])
        records = [r for r in out.strip("\n").split(RS)]
        if records and records[-1].strip() == "":
            records = records[:-1]
        header, body = records[0].lstrip("\n").split(FS), records[1:]
        rows = []
        for rec in body:
            vals = rec.lstrip("\n").split(FS)
            rows.append(Row(header, [_convert(v, t) for v, t in zip(vals, rtypes)]))
        return Result(rows)

    _TYPE_ALIASES = {"timestamptz": "timestamp with time zone", "int4": "integer", "int8": "bigint", "int2": "smallint",
                     "bool": "boolean", "float8": "double precision", "varchar": "character varying"}

    def _typename(self, t: str) -> str:
        t = t.strip().strip('"')
        return self._TYPE_ALIASES.get(t, t)

    async def commit(self):
        if self.in_tx:
            self._raw("ROLLBACK" if self.failed else "COMMIT")
            self.in_tx = False

    async def rollback(self):
        if self.in_tx:
            self._raw("ROLLBACK")
            self.in_tx = False

    def close(self):
        try:
            if self.in_tx:
                self._raw("ROLLBACK")          # like closing an AsyncSession without commit
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


class DB:
    """app.db.db (commit=True) or the admin app's db.db (commit=False: callers must commit)."""

    def __init__(self, commit: bool):
        self.auto_commit = commit
        self.sessions = 0
        self.lock = threading.Lock()

    @contextlib.asynccontextmanager
    async def get_session(self):
        s = Session()
        with self.lock:
            self.sessions += 1
        try:
            yield s
            if self.auto_commit:
                await s.commit()
        except BaseException:
            await s.rollback()
            raise
        finally:
            s.close()
