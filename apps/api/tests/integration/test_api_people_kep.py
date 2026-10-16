"""GET /v1/people* against the loaded `kep` graph at the pinned data (read-only)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import live_graph_pinned
from fastapi.testclient import TestClient

from app.db.falkordb import FalkorPool
from app.main import create_app
from app.settings import Settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    pool = FalkorPool(Settings())
    try:
        loaded = live_graph_pinned(pool)
    except Exception:  # noqa: BLE001
        loaded = False
    finally:
        pool.close()
    if not loaded:
        pytest.skip("graph `kep` is not loaded at the pinned data")
    with TestClient(create_app()) as c:
        yield c


def test_mrunalp(client: TestClient) -> None:
    body = client.get("/v1/people/MrunalP").json()
    assert body["login"] == "mrunalp" and body["url"] == "https://github.com/mrunalp"
    assert {(r["org"], r["org_kind"], r["role"]) for r in body["roles"]} == {
        ("sig-node", "SIG", "chair"), ("sig-node", "SIG", "tech_lead"),
    }  # fmt: skip
    assert all(r["source_url"].endswith("/sigs.yaml") for r in body["roles"])
    assert [k["number"] for k in body["keps"]["authored"]] == [2000, 2040, 2413, 2712]
    assert (len(body["keps"]["reviews"]), len(body["keps"]["approves"])) == (28, 47)
    kubelet = [o for o in body["owners"] if o["directory"] == "cmd/kubelet"]
    assert kubelet and kubelet[0]["role"] == "approver" and kubelet[0]["via_alias"] == "sig-node-approvers"
    assert kubelet[0]["source_url"].startswith("https://github.com/kubernetes/kubernetes/blob/")
    assert kubelet[0]["source_url"].endswith("/cmd/kubelet/OWNERS")
    conn = body["connectivity"]
    assert conn["rank"] == 3 and conn["of"] >= 600 and conn["score"] > 0


def test_decisions_newest_first_with_urls(client: TestClient) -> None:
    decisions = client.get("/v1/people/mrunalp").json()["decisions"]
    assert len(decisions) == 100
    assert [d["decided_at_iso"] for d in decisions] == sorted((d["decided_at_iso"] for d in decisions), reverse=True)
    assert all(d["url"].startswith("https://github.com/") and d["role"] for d in decisions)
    assert decisions[0]["key"].startswith("dec:") and decisions[0]["kep_number"] == 5359


def test_prr_approver_and_direct_owner(client: TestClient) -> None:
    john = client.get("/v1/people/johnbelamaric").json()
    assert len(john["keps"]["prr_approved"]) == 116 and john["connectivity"]["rank"] == 1
    assert {p["stage"] for p in john["keps"]["prr_approved"]} <= {"alpha", "beta", "stable", "deprecated"}
    dchen = client.get("/v1/people/dchen1107").json()
    assert {(o["directory"], o["role"], o["via_alias"]) for o in dchen["owners"]} >= {("cmd", "approver", None)}


def test_bot_and_unknown(client: TestClient) -> None:
    bot = client.get("/v1/people/k8s-ci-robot").json()
    assert bot["is_bot"] is True and bot["connectivity"] is None and bot["decisions"]
    res = client.get("/v1/people/not-a-real-login-xyz")
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"
