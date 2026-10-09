"""GET /api/modules and GET /api/modules/{module_id}/config."""

import json

import pytest

from app import repositories
from tests.utils import bearer, error_of, register_ok, sql

LIST_KEYS = {"module_id", "title", "description", "difficulty", "thumbnail_url"}
CONFIG_KEYS = {"module_id", "scene_name", "cdn_bundle_url", "difficulty", "config"}
SEED_ORDER = ["cell-explore", "cell-puzzle", "cell-process", "cell-quiz"]


@pytest.fixture
def token(client):
    return register_ok(client)["token"]


# ============================================================
# LIST
# ============================================================

def test_list_modules_returns_seed_in_order_with_exact_keys(client, seeded_modules, token):
    response = client.get("/api/modules", headers=bearer(token))

    assert response.status_code == 200
    modules = response.json()
    assert isinstance(modules, list)
    assert [m["module_id"] for m in modules] == SEED_ORDER
    for module in modules:
        assert set(module) == LIST_KEYS
        assert module["title"] and module["description"]
        assert isinstance(module["difficulty"], int)
        assert module["thumbnail_url"] is None
    assert modules[0]["title"] == "Explore the Cell"


def test_list_modules_reads_thumbnail_from_config_display(client, seeded_modules, token):
    display = {"display": {"description": "With picture", "thumbnail_url": "https://cdn.example.com/t.png"}}
    sql(
        "INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url, difficulty, config) "
        "VALUES ('zz-temp', 'Temp', 'GameScene_Temp', 'https://cdn.example.com/x', 9, $1::jsonb)",
        json.dumps(display),
    )
    try:
        modules = client.get("/api/modules", headers=bearer(token)).json()
        temp = next(m for m in modules if m["module_id"] == "zz-temp")
        assert temp["thumbnail_url"] == "https://cdn.example.com/t.png"
        assert temp["description"] == "With picture"
        assert modules[-1]["module_id"] == "zz-temp"  # highest difficulty sorts last
    finally:
        sql("DELETE FROM modules WHERE module_id = 'zz-temp'")


def test_list_modules_handles_module_without_display_metadata(client, seeded_modules, token):
    sql("INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url) "
        "VALUES ('zz-bare', 'Bare', 'GameScene_Bare', 'https://cdn.example.com/b')")
    try:
        modules = client.get("/api/modules", headers=bearer(token)).json()
        bare = next(m for m in modules if m["module_id"] == "zz-bare")
        assert bare["description"] == ""
        assert bare["thumbnail_url"] is None
    finally:
        sql("DELETE FROM modules WHERE module_id = 'zz-bare'")


def test_list_modules_empty_is_empty_array(client, token):
    sql("DELETE FROM modules")  # later tests re-seed through the seeded_modules fixture
    response = client.get("/api/modules", headers=bearer(token))
    assert response.status_code == 200
    assert response.json() == []


def test_list_modules_requires_token(client):
    response = client.get("/api/modules")
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_MISSING"


# ============================================================
# CONFIG
# ============================================================

@pytest.mark.parametrize("module_id, scene_name", [
    ("cell-explore", "GameScene_CellExplore"),
    ("cell-puzzle", "GameScene_CellPuzzle"),
    ("cell-process", "GameScene_CellProcess"),
    ("cell-quiz", "GameScene_CellQuiz"),
])
def test_module_config_matches_pdf_contract(client, seeded_modules, token, module_id, scene_name):
    response = client.get(f"/api/modules/{module_id}/config", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == CONFIG_KEYS
    assert body["module_id"] == module_id
    assert body["scene_name"] == scene_name
    assert body["cdn_bundle_url"] == f"https://cdn.example.com/bundles/{module_id}"
    assert isinstance(body["difficulty"], int)
    assert isinstance(body["config"], dict)
    assert body["config"]["display"]["description"]


def test_module_config_unknown_module_is_404(client, seeded_modules, token):
    response = client.get("/api/modules/does-not-exist/config", headers=bearer(token))
    assert response.status_code == 404
    assert error_of(response)["code"] == "MODULE_NOT_FOUND"


def test_module_config_requires_token(client, seeded_modules):
    response = client.get("/api/modules/cell-explore/config")
    assert response.status_code == 401
    assert error_of(response)["code"] == "TOKEN_MISSING"


def test_module_ids_are_bound_parameters_not_sql(client, seeded_modules, token):
    response = client.get("/api/modules/x' OR '1'='1/config", headers=bearer(token))
    assert response.status_code == 404


# ============================================================
# GENERIC ERROR FORMAT
# ============================================================

def test_unexpected_error_returns_contract_500(client, token, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(repositories, "list_modules", boom)

    response = client.get("/api/modules", headers=bearer(token))

    assert response.status_code == 500
    detail = error_of(response)
    assert detail["code"] == "INTERNAL_ERROR"
    assert "simulated failure" not in response.text


def test_unknown_route_uses_contract_format(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert error_of(response)["code"] == "NOT_FOUND"
