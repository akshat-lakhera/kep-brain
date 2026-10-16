"""Track 1 tools against the loaded `kep` graph at the pinned data; read-only (values looked up 2026-10-15)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from conftest import live_graph_pinned

from app.db.falkordb import GRAPH_KEP, FalkorPool, Role
from app.settings import Settings
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import TOOLS

FINDINGS_TOTAL = 59
K4671 = "keps/sig-scheduling/4671-gang-scheduling"
K583 = "keps/sig-scheduling/583-coscheduling"


@pytest.fixture(scope="module")
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings())
    try:
        loaded = live_graph_pinned(p, "MATCH (f:Finding) RETURN count(f)", FINDINGS_TOTAL)
    except Exception:  # noqa: BLE001
        loaded = False
    if not loaded:
        p.close()
        pytest.skip("graph `kep` is not loaded at the pinned data")
    yield p
    p.close()


async def call(pool: FalkorPool, name: str, **params: Any) -> ToolResult:
    result = await TOOLS[name].invoke(ToolContext(pool=pool), params)
    assert result.evidence, name
    assert all(e.url.startswith("https://github.com/") for e in result.evidence), name
    evidence_keys = {e.key for e in result.evidence}
    for path in result.paths:
        assert path[0] in evidence_keys and path[-1] in evidence_keys, path
    return result


async def test_who_knows_kep(pool: FalkorPool) -> None:
    r = await call(pool, "who_knows", topic_or_kep=4671, limit=5)
    assert r.rows[0]["scope"]["kep"] == K4671 and r.rows[0]["scope"]["keps_in_scope"] == 1
    top = r.rows[1]
    assert top["person"]["key"] == "dom4ha" and top["score"] == 10
    assert top["by_rel"] == {"AUTHORED": 1, "APPROVES": 1, "REVIEWS": 1, "SUBMITTED": 1, "COMMENTED": 1}
    assert [x["person"]["key"] for x in r.rows[2:4]] == ["wojtek-t", "sanposhiho"]
    assert ["dom4ha", "AUTHORED", K4671] in r.paths
    assert any(p[1] == "COMMENTED" and p[3] == "EVIDENCED_BY" and p[-1] == K4671 for p in r.paths)


async def test_who_knows_term_and_sig_pagerank(pool: FalkorPool) -> None:
    r = await call(pool, "who_knows", topic_or_kep="gang scheduling", limit=5)
    assert r.rows[0]["scope"]["keps_in_scope"] == 18
    assert r.rows[1]["person"]["key"] == "dom4ha" and r.rows[1]["score"] == 92
    r = await call(pool, "who_knows", sig="sig-scheduling", metric="pagerank", limit=5)
    assert r.rows[0]["scope"]["keps_in_scope"] == 59
    ranked = [x["person"]["key"] for x in r.rows[1:]]
    assert ranked[:2] == ["johnbelamaric", "wojtek-t"]
    scores = [x["decision_pagerank"] for x in r.rows[1:]]
    assert scores == sorted(scores, reverse=True) and scores[0] > 0


async def test_impact_of_change_4671(pool: FalkorPool) -> None:
    r = await call(pool, "impact_of_change", kep_ref=4671)
    summary = r.rows[0]
    assert summary["by_hop"]["1"] == {"keps": 10, "feature_gates": 5, "sigs": 1, "people": 10, "open_issues": 1}
    hop1 = r.rows[1]
    assert hop1["hop"] == 1 and 583 in {k["number"] for k in hop1["keps"]}
    assert [s["key"] for s in hop1["sigs"]] == ["sig-scheduling"]
    assert [i["key"] for i in hop1["open_issues"]] == ["kubernetes/enhancements#4671"]
    hop2 = r.rows[2]
    assert {2232, 1287, 268, 2926, 5690} == {k["number"] for k in hop2["keps"]}
    assert [K4671, "GATED_BY", "GenericWorkload"] in r.paths
    assert len(r.paths) == summary["reached"] == 66


async def test_impact_depth3_grows(pool: FalkorPool) -> None:
    r = await call(pool, "impact_of_change", kep_ref=1287, depth=3)
    assert set(r.rows[0]["by_hop"]) == {"1", "2", "3"}
    assert r.rows[0]["by_hop"]["1"]["keps"] == 8


async def test_path_to_decision_direct(pool: FalkorPool) -> None:
    r = await call(pool, "path_to_decision", person="sanposhiho", kep_ref=4671, path_count=1)
    row = r.rows[0]
    assert row["length"] == 1 and row["edge_types"] == ["DECIDED_BY"]
    assert "approver" in row["roles"]
    assert row["decision"]["url"] == "https://github.com/kubernetes/enhancements/pull/6349"


async def test_path_to_decision_multi_hop(pool: FalkorPool) -> None:
    r = await call(pool, "path_to_decision", person="dom4ha", kep_ref=583, path_count=1)
    row = r.rows[0]
    assert row["length"] == 3 and row["path"][0] == "dom4ha" and row["path"][-2] == "ABOUT"
    assert row["path"][-3] == K583 and row["decision"]["kep_path"] == K583
    r = await TOOLS["path_to_decision"].invoke(ToolContext(pool=pool), {"person": "no-such-login-x", "kep_ref": 583})
    assert r.rows == [{"person_not_found": "no-such-login-x"}]


async def test_changed_since_v137_status(pool: FalkorPool) -> None:
    r = await call(pool, "changed_since", release="v1.37", sig="sig-scheduling", fields=["status"])
    assert r.rows[0]["after"] == "2026-08-26T16:29:12Z" and r.rows[0]["changes"] == 3
    got = {(x["kep"]["number"], x["change"]["to_value"], x["pull_request"]["number"]) for x in r.rows[1:]}
    assert got == {(5981, "implementable", 5987), (6080, "implementable", 6255), (6406, "implementable", 6408)}
    assert all(x["change"]["url"].startswith("https://github.com/") for x in r.rows[1:])
    assert {"person": "pohly", "role": "approver"} in [
        {"person": d["person"]["key"], "role": d["role"]} for d in r.rows[1]["deciders"]
    ]
    r = await call(pool, "changed_since", release="v1.37", sig="sig-scheduling", fields=["status", "stage"])
    assert r.rows[0]["by_field"] == {"stage": 13, "status": 3}


async def test_changed_since_future_release(pool: FalkorPool) -> None:
    future = pool.run_sync(
        Role.READER,
        GRAPH_KEP,
        "MATCH (r:Release) WHERE r.is_future RETURN r.key ORDER BY r.key DESC LIMIT 1",
        read_only=True,
        timeout_ms=2000,
    ).rows
    if not future:
        pytest.skip("every Release in the graph has shipped")
    r = await TOOLS["changed_since"].invoke(ToolContext(pool=pool), {"release": future[0][0]})
    assert r.rows[0]["not_released_yet"] is True
