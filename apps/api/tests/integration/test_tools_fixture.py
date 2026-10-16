"""Every v1 tool against a throwaway fixture graph in the `kep` contract shape."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fixture_graph import STATEMENTS

from app.db.falkordb import FalkorPool, Role
from app.settings import Settings
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import TOOLS

GRAPH = "test_lanec_tools"


@pytest.fixture(scope="module")
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings())
    try:
        p.list_graphs()
    except Exception:  # noqa: BLE001
        pytest.skip("FalkorDB not reachable")
    if GRAPH in p.list_graphs():
        p.graph(Role.WRITER, GRAPH).delete()
    for stmt in STATEMENTS:
        p.run_sync(Role.WRITER, GRAPH, stmt, read_only=False, timeout_ms=10000)
    yield p
    p.graph(Role.WRITER, GRAPH).delete()
    p.close()


@pytest.fixture
async def ctx(pool: FalkorPool) -> AsyncIterator[ToolContext]:
    yield ToolContext(pool=pool, graph=GRAPH)


async def call(ctx: ToolContext, name: str, **params: Any) -> ToolResult:
    return await TOOLS[name].invoke(ctx, params)


def keys(result: ToolResult) -> set[str]:
    return {e.key for e in result.evidence}


async def test_find_entities_number_and_nearest(ctx: ToolContext) -> None:
    r = await call(ctx, "find_entities", query="KEP-583")
    assert r.rows[0]["match"] == "exact" and r.rows[0]["key"].endswith("583-coscheduling")
    r = await call(ctx, "find_entities", query="GangScheduling")
    assert r.rows[0] == {"no_exact_match": "GangScheduling"}
    nearest = [row for row in r.rows[1:] if row.get("key", "").endswith("4671-gang-scheduling")]
    assert nearest and nearest[0]["gates"] == ["GenericWorkload"]
    assert all(row.get("match") != "exact" for row in r.rows[1:])


async def test_ambiguous_number_returns_candidates(ctx: ToolContext) -> None:
    r = await call(ctx, "get_kep", kep_ref=2133)
    assert len(r.rows[0]["candidates"]) == 2


async def test_get_kep_card(ctx: ToolContext) -> None:
    r = await call(ctx, "get_kep", kep_ref="4671")
    row = r.rows[0]
    assert [g["key"] for g in row["feature_gates"]] == ["GenericWorkload"]
    assert {x["kep"]["number"] for x in row["replaces"]} == {583, 5832}
    assert row["prr_approvers"][0]["person"]["key"] == "soltysh"


async def test_find_contradictions_scope_kep(ctx: ToolContext) -> None:
    r = await call(ctx, "find_contradictions", kep_ref=583)
    hit = r.rows[0]
    assert hit["finding"]["kind"] == "active_status_closed_issue"
    assert "kubernetes/enhancements#583" in keys(r)
    corpus = await call(ctx, "find_contradictions")
    assert corpus.rows[0]["total"] == 1


async def test_kep_relations_lineage(ctx: ToolContext) -> None:
    r = await call(ctx, "kep_relations", kep_ref=4671, mode="lineage", depth=2, direction="outgoing")
    reached = {row["kep"]["number"] for row in r.rows[1:]}
    assert reached == {583, 5832}
    assert r.paths


async def test_trace_decision_and_history(ctx: ToolContext) -> None:
    r = await call(ctx, "trace_decision", kep_ref=1287)
    row = r.rows[0]
    assert row["people"][0]["person"]["key"] == "natasha41575"
    assert row["pull_requests"][0]["number"] == 5761
    h = await call(ctx, "status_history", kep_ref=1287)
    assert h.rows[1]["change"]["to_value"] == "implemented"


async def test_path_between_skips_bots(ctx: ToolContext) -> None:
    r = await call(ctx, "path_between", from_label="Person", from_key="soltysh", to_label="KEP", to_key="4671")
    assert r.rows[0]["length"] == 1
    assert r.rows[0]["edges"][0]["type"] == "PRR_APPROVED"


async def test_who_tools(ctx: ToolContext) -> None:
    r = await call(ctx, "who_approves", kep_ref=1287)
    assert r.rows[0]["past_decisions"][0]["people"][0]["person"]["key"] == "natasha41575"
    o = await call(ctx, "who_owns", directory_path="pkg/kubelet")
    assert o.rows[0]["owners_data_loaded"] is False
    g = await call(ctx, "who_owns", feature_gate="GenericWorkload")
    assert g.rows[0]["owning_sig"][0]["key"] == "sig-scheduling"


async def test_rank_whats_changed_findings_draft(ctx: ToolContext) -> None:
    r = await call(ctx, "rank_people", sig="sig-scheduling")
    assert r.rows[0]["metric_used"] == "pagerank"  # the fixture stores Person.pagerank as the worker does
    by_degree = await call(ctx, "rank_people", sig="sig-scheduling", metric="degree")
    assert by_degree.rows[0]["metric_used"] == "degree"
    assert all(row["person"]["key"] != "k8s-ci-robot" for row in r.rows[1:])
    w = await call(ctx, "whats_changed", since="2025-01-01")
    assert w.rows[0]["keps_changed"] == 1
    f = await call(ctx, "recall_findings", kep_ref=583)
    assert f.rows[0]["finding"]["state"] == "open"
    d = await call(
        ctx, "draft_stale_doc_issue", finding_key="fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling"
    )
    assert (
        d.rows[0]["posted"] is False
        and f"{'https://github.com/kubernetes/enhancements'}/issues/583" in d.rows[0]["body"]
    )


async def test_deterministic(ctx: ToolContext) -> None:
    for name, params in [
        ("kep_relations", {"kep_ref": 4671}),
        ("find_contradictions", {}),
        ("get_kep", {"kep_ref": 583}),
    ]:
        a = await TOOLS[name].invoke(ctx, params)
        b = await TOOLS[name].invoke(ctx, params)
        assert a.rows == b.rows


async def test_schema_tool(ctx: ToolContext) -> None:
    r = await call(ctx, "get_graph_schema")
    assert "KEP" in r.rows[0]["labels"]
