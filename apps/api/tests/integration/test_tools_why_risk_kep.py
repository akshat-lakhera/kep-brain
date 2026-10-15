"""why_designed, contested_points, knowledge_risk, /v1/risk and the /v1/changes label filter against the
loaded `kep` graph at the pinned data; read-only (values looked up 2026-10-15 after `worker sync-tickets`)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.falkordb import GRAPH_KEP, FalkorPool, Role
from app.main import create_app
from app.settings import Settings
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import TOOLS

K4671 = "keps/sig-scheduling/4671-gang-scheduling"
README = (
    "https://github.com/kubernetes/enhancements/blob/8659e382efab7340d70de52432ee8f3d9979b797/" + K4671 + "/README.md"
)
REVIEW_COMMENTS = 12087


@pytest.fixture(scope="module")
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings())
    try:
        loaded = (
            GRAPH_KEP in p.list_graphs()
            and p.run_sync(
                Role.READER,
                GRAPH_KEP,
                "MATCH (c:Comment {kind: 'review_comment'}) RETURN count(c)",
                read_only=True,
                timeout_ms=5000,
            ).rows[0][0]
            >= REVIEW_COMMENTS
        )
    except Exception:  # noqa: BLE001
        loaded = False
    if not loaded:
        p.close()
        pytest.skip("graph `kep` is not loaded with review discussion at the pinned data")
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


async def test_why_designed_4671(pool: FalkorPool) -> None:
    r = await call(pool, "why_designed", kep_ref=4671)
    head = r.rows[0]
    assert head["kep"]["key"] == K4671
    assert head["parts_found"] == ["summary", "motivation", "goals", "non_goals", "proposal", "drawbacks", "risks"]
    assert head["parts_missing"] == ["alternatives"]
    assert {x["kep"]["number"] for x in head["replaces"]} == {583, 5832}
    by_part = {row["part"]: row for row in r.rows[1:]}
    assert by_part["goals"]["url"] == README + "#goals" and by_part["goals"]["chars"] == 1190
    assert by_part["risks"]["url"] == README + "#risks-and-mitigations" and by_part["risks"]["chars"] == 2694
    assert by_part["summary"]["excerpt"].startswith("In this KEP, kube-scheduler is modified to support gang")
    assert all(len(row["excerpt"]) <= 1200 and row["url"].startswith(README + "#") for row in r.rows[1:])


async def test_why_designed_split_proposal_1287(pool: FalkorPool) -> None:
    r = await call(pool, "why_designed", kep_ref=1287)
    assert r.rows[0]["parts_missing"] == []
    proposal = next(row for row in r.rows[1:] if row["part"] == "proposal")
    assert proposal["heading"] == "API Changes" and proposal["url"].endswith("/README.md#api-changes")


async def test_contested_points_4671(pool: FalkorPool) -> None:
    r = await call(pool, "contested_points", kep_ref=4671, limit=20)
    head = r.rows[0]
    assert (head["comments"], head["pull_requests"], head["people"]) == (413, 6, 22)
    assert head["first_iso"] == "2025-09-23T10:07:49Z"
    assert [(a["login"], a["comments"]) for a in head["top_commenters"][:2]] == [("wojtek-t", 88), ("macsko", 73)]
    first = r.rows[1]
    assert first["author"]["login"] == "ricardomaraschini" and first["pull_request"]["number"] == 5558
    assert first["url"] == "https://github.com/kubernetes/enhancements/pull/5558#discussion_r2371805189"
    assert first["path"] == K4671 + "/README.md" and first["source"] == "review_thread"
    assert len(r.rows) == 21 and r.truncated
    times = [row["at_iso"] for row in r.rows[1:]]
    assert times == sorted(times)


async def test_knowledge_risk_tool(pool: FalkorPool) -> None:
    r = await call(pool, "knowledge_risk")
    head = r.rows[0]
    assert head["counts"] == {"active_keps": 141, "single_approver": 71, "without_approver": 5, "idle_people": 75}
    assert head["thresholds"]["idle_since_iso"] == "2025-12-17T20:01:55Z"
    load = [row for row in r.rows if row.get("kind") == "load"]
    assert (load[0]["login"], load[0]["active_keps"], load[0]["share"]) == ("dchen1107", 42, 0.298)
    assert ["janetkuo", "APPROVES", "keps/sig-apps/2255-pod-cost"] in r.paths


@pytest.fixture(scope="module")
def client(pool: FalkorPool) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def test_risk_route(client: TestClient) -> None:
    body = client.get("/v1/risk").json()
    assert body["counts"]["single_approver"] == 71 and len(body["single_approver"]) == 71
    row = next(x for x in body["single_approver"] if x["kep"]["number"] == 2255)
    assert row["approver"] == {"login": "janetkuo", "url": "https://github.com/janetkuo"}
    assert row["source_url"].endswith("/keps/sig-apps/2255-pod-cost/kep.yaml")
    idle = next(x for x in body["idle"] if x["login"] == "derekwaynecarr")
    assert idle["last_decision_iso"] == "2024-10-10T12:02:23Z" and idle["active_keps"] == 13
    sched = client.get("/v1/risk", params={"sig": "sig-scheduling"}).json()
    assert sched["counts"]["active_keps"] == 41 and sched["counts"]["single_approver"] == 15
    assert sched["load"][0]["login"] == "dom4ha" and sched["load"][0]["share"] == 0.512
    assert client.get("/v1/risk", params={"sig": "sig-nope"}).status_code == 404


def test_changes_hide_automation_labels(client: TestClient) -> None:
    default = client.get("/v1/changes", params={"limit": 500}).json()
    full = client.get("/v1/changes", params={"limit": 500, "include_labels": "true"}).json()
    assert default["counts"]["label_changes"] == 371 and full["counts"]["label_changes"] == 722
    assert default["counts"]["keps_changed"] == full["counts"]["keps_changed"] == 96
    assert not any(i["field"].startswith("tracked/") for i in default["items"] if i["kind"] == "label")
    assert any(i["field"].startswith("tracked/") for i in full["items"] if i["kind"] == "label")


async def test_whats_changed_hides_automation_labels(pool: FalkorPool) -> None:
    def fields(r: ToolResult) -> list[str]:
        return [str(c.get("field")) for row in r.rows[1:] for c in row.get("changes", [])]

    quiet = await call(pool, "whats_changed", since="v1.37", kinds=["label"], limit=200)
    loud = await call(pool, "whats_changed", since="v1.37", kinds=["label"], limit=200, include_labels=True)
    assert fields(quiet) and not any(f.startswith("tracked/") for f in fields(quiet))
    assert any(f.startswith("tracked/") for f in fields(loud))
