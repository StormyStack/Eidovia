"""
Load the DNA curriculum into pgvector, one chunk per sub-section,
each tagged with its HOE level (1-4).

Run from services/ai on the host, with the venv active:
    python -m scripts.load_curriculum

Re-running replaces the existing chunks for DNA_BIOLOGY_001.
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote

import asyncpg
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = SCRIPT_DIR.parent
ROOT_DIR = SERVICE_DIR.parent.parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MODULE_ID = "DNA_BIOLOGY_001"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
MAX_CHUNK_CHARS = 1000  # all-MiniLM-L6-v2 truncates input beyond ~256 tokens

DB_PASSWORD = quote(os.getenv("DB_PASSWORD", ""), safe="")
DB_USER = os.getenv("POSTGRES_USER", "appuser")
DB_NAME = os.getenv("POSTGRES_DB", "eidovia")
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "6543")
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# HOE level for each sub-section (draft mapping, review before submission)
#   1 = General Overview
#   2 = Structural Components
#   3 = Sub-Components
#   4 = Functional or Molecular Detail
HOE_LEVELS = {
    # Section 1: DNA structure
    "The Double Helix Structure (NCBI)": 1,
    "Nitrogenous Bases (Khan Academy)": 2,
    "Base Pairing and Chargaff's Rules": 2,
    "Nucleotide Structure (OpenStax Biology)": 3,
    # Section 2: DNA replication
    "Semi-Conservative Replication (OpenStax Biology)": 4,
    "DNA Polymerase and Enzyme Catalysis (NCBI)": 4,
    "Leading and Lagging Strands (Khan Academy)": 4,
    "DNA Replication Process Timeline": 4,
    # Section 3: Gene expression
    "Transcription Overview (OpenStax Biology)": 4,
    "mRNA Processing in Eukaryotes (NCBI)": 4,
    "Translation Process (Khan Academy)": 4,
    # Section 4: Mutations
    "Types of Mutations (OpenStax Biology)": 3,
    "Mutation Causes and Prevention (NCBI)": 4,
    "Natural Selection and Evolution (Khan Academy)": 1,
    # Section 5: Gene regulation
    "Transcriptional Control (OpenStax Biology)": 4,
    "DNA Methylation (NCBI)": 4,
    "Histone Modifications and Chromatin Remodeling (Khan Academy)": 4,
}

SUBSECTION_RE = re.compile(r"^\*\*(.+?)\*\*$")


def parse_chunks(text: str) -> list[dict]:
    """Split the curriculum into one chunk per bold sub-section."""
    chunks: list[dict] = []
    section = None
    title = None
    body: list[str] = []

    def flush():
        if title is not None and body:
            chunks.append({
                "section": section,
                "title": title,
                "text": " ".join(" ".join(body).split()),
            })

    for raw in text.splitlines():
        line = raw.strip()

        if line.startswith("# END"):
            break
        if line.startswith("## SECTION"):
            flush()
            title, body = None, []
            section = line.lstrip("#").strip()
            continue

        match = SUBSECTION_RE.match(line)
        if match:
            flush()
            title = match.group(1).strip()
            body = []
            continue

        if not line or line.startswith("#") or line == "---":
            continue
        if title is not None:
            body.append(line)

    flush()
    return chunks


async def main():
    data_file = SERVICE_DIR / "data" / "expanded_dna_curriculum.txt"
    logger.info(f"Reading {data_file}")
    text = data_file.read_text(encoding="utf-8")

    parsed = parse_chunks(text)

    # Fail loudly rather than silently skipping an unmapped sub-section
    unmapped = [c["title"] for c in parsed if c["title"] not in HOE_LEVELS]
    if unmapped:
        raise SystemExit(f"No HOE level for: {unmapped}")

    chunks = []
    for c in parsed:
        content = f"{c['title']}: {c['text']}"
        if len(content) > MAX_CHUNK_CHARS:
            logger.warning(f"Chunk too long ({len(content)} chars): {c['title']}")
        chunks.append({
            "content": content,
            "level": HOE_LEVELS[c["title"]],
            "section": c["section"],
        })
    logger.info(f"Parsed {len(chunks)} chunks")

    logger.info(f"Loading embedding model {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    embeddings = model.encode([c["content"] for c in chunks])

    logger.info(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url, difficulty) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
                MODULE_ID, "DNA & Cell Biology", "dna_scene",
                "https://cdn.example.com/dna-bundle.zip", 3,
            )
            await conn.execute(
                "DELETE FROM document_chunks WHERE module_id = $1", MODULE_ID
            )
            for chunk, emb in zip(chunks, embeddings):
                emb_str = "[" + ", ".join(f"{x:.8f}" for x in emb) + "]"
                await conn.execute(
                    "INSERT INTO document_chunks "
                    "(module_id, content, embedding, hoe_level, section_title) "
                    "VALUES ($1, $2, $3::vector(384), $4, $5)",
                    MODULE_ID, chunk["content"], emb_str,
                    chunk["level"], chunk["section"],
                )
    finally:
        await conn.close()

    counts = {}
    for c in chunks:
        counts[c["level"]] = counts.get(c["level"], 0) + 1
    logger.info(f"Inserted {len(chunks)} chunks. Per level: {dict(sorted(counts.items()))}")


if __name__ == "__main__":
    asyncio.run(main())