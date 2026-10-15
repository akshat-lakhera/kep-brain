"""GET /v1/sigs* against the loaded `kep` graph at the pinned data (read-only)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.falkordb import GRAPH_KEP, FalkorPool, Role
from app.main import create_app
from app.settings import Settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    pool = FalkorPool(Settings())
    try:
        loaded = (
            GRAPH_KEP in pool.list_graphs()
            and pool.run_sync(
                Role.READER, GRAPH_KEP, "MATCH (k:KEP) RETURN count(k)", read_only=True, timeout_ms=2000
            ).rows[0][0]
            >= 238
        )
    except Exception:  # noqa: BLE001
        loaded = False
    finally:
        pool.close()
    if not loaded:
        pytest.skip("graph `kep` is not loaded at the pinned data")
    with TestClient(create_app()) as c:
        yield c


def test_sig_list(client: TestClient) -> None:
    items = client.get("/v1/sigs").json()["items"]
    assert len(items) == 24 and sum(i["keps"] for i in items) == 238
    assert [i["key"] for i in items[:3]] == ["sig-apps", "sig-node", "sig-scheduling"]
    assert all(i["in_scope"] for i in items[:3]) and not any(i["in_scope"] for i in items[3:])
    node = items[1]
    assert (node["keps"], node["open_findings"]) == (139, 30)
    assert {p["login"] for p in node["chairs"]} == {"mrunalp", "haircommander", "sergeykanzhelev"}
    assert {p["login"] for p in node["tech_leads"]} == {"dchen1107", "mrunalp", "derekwaynecarr"}
    assert all(i["url"].startswith("https://github.com/kubernetes/community/") for i in items)


def test_sig_page(client: TestClient) -> None:
    body = client.get("/v1/sigs/sig-scheduling").json()
    assert body["keps_by_status"] == {"implementable": 38, "implemented": 18, "provisional": 3}
    assert len(body["keps"]) == 59 and body["open_findings"] == 20 and len(body["findings"]) == 20
    assert all("human_verdict" in f for f in body["findings"])
    assert body["subprojects"] and all(s["name"] and s["url"].startswith("https://") for s in body["subprojects"])
    leads = {p["login"]: p["roles"] for p in body["people"][:5]}
    assert "tech_lead" in leads["dom4ha"]
    assert client.get("/v1/sigs/sig-does-not-exist").status_code == 404
