"""Lease protocol, handoffs and the finding journey on throwaway `test_ops_*` / `test_kep_*` graphs."""

from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from ulid import ULID

from app.db.falkordb import FalkorPool, Role
from app.settings import Settings
from app.worker import coordinate as co
from app.worker.freshness import Completion, run_freshness_once

ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
A_URL = "https://github.com/kubernetes/enhancements/blob/pin/keps/sig-scheduling/583-coscheduling/kep.yaml"
B_URL = "https://github.com/kubernetes/enhancements/issues/583"
FINDING = "fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling"

SEED_KEP = """
CREATE (k:KEP {key: 'keps/sig-scheduling/583-coscheduling', number: 583, title: 'Coscheduling', status: 'provisional',
  url: 'https://github.com/kubernetes/enhancements/tree/pin/keps/sig-scheduling/583-coscheduling'})
CREATE (i:Issue:Ticket {key: 'kubernetes/enhancements#583', number: 583, state: 'closed', state_reason: 'completed',
  url: $b_url})
CREATE (d:Document {key: 'kubernetes/enhancements:keps/sig-scheduling/583-coscheduling/kep.yaml', kind: 'kep_yaml',
  url: $a_url})
CREATE (k)-[:TRACKED_BY]->(i)
CREATE (f:Finding {key: $fkey, kind: 'active_status_closed_issue', kep_path: k.key, state: 'open',
  a_label: 'kep.yaml status', a_value: 'provisional', a_url: $a_url,
  b_label: 'issue #583 state', b_value: 'closed (completed)', b_url: $b_url,
  suggested_fix: 'set_status_implemented', detected_at: 1, detected_at_iso: 'x'})
CREATE (f)-[:ABOUT]->(k)
CREATE (f)-[:EVIDENCED_BY {evidence_kind: 'kep_yaml'}]->(d)
CREATE (f)-[:EVIDENCED_BY {evidence_kind: 'tracking_issue'}]->(i)
"""


class FakeLlm:
    model = "fake-model"

    def __init__(self, mode: str = "good") -> None:
        self.mode = mode
        self.calls = 0

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        self.calls += 1
        rows = json.loads(messages[1]["content"])["evidence"]
        issue = next(r for r in rows if r["type"] == "Issue")["evidence_id"]
        cited = "cccccccccccc" if self.mode == "bad_citation" else issue
        body = {
            "triage_verdict": "needs_human" if self.mode == "needs_human" else "confirmed",
            "assessment": f"Tracking issue is closed as completed [{cited}] while kep.yaml says provisional.",
            "suggested_fix": "set_status_implemented",
            "confidence": 0.9,
        }
        return Completion(json.dumps(body), 1000, 200)


@pytest.fixture()
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings(_env_file=ENV_FILE if ENV_FILE.exists() else None))  # type: ignore[call-arg]
    try:
        p.list_graphs()
    except Exception as exc:  # noqa: BLE001 - any connection problem skips the integration test
        pytest.skip(f"FalkorDB not reachable: {exc}")
    yield p
    p.close()


@pytest.fixture()
def graphs(pool: FalkorPool) -> Iterator[tuple[str, str]]:
    ops, kep = f"test_ops_{ULID()}".lower(), f"test_kep_{ULID()}".lower()
    params = {"a_url": A_URL, "b_url": B_URL, "fkey": FINDING}
    pool.run_sync(Role.WRITER, kep, SEED_KEP, params, read_only=False, timeout_ms=10000)
    yield ops, kep
    existing = pool.list_graphs()
    for name in (ops, kep):
        if name in existing:
            pool.graph(Role.WRITER, name).delete()


@pytest.fixture()
def settings() -> Settings:
    return Settings(_env_file=None, findings_agent_daily_usd=1.0)  # type: ignore[call-arg]


def q(pool: FalkorPool, graph: str, query: str, **params: Any) -> list[list[Any]]:
    return pool.run_sync(Role.WRITER, graph, query, params, read_only=False, timeout_ms=10000).rows


def add_task(
    pool: FalkorPool, ops: str, key: str, status: str, attempts: int = 0, lease_offset_ms: int | None = None
) -> None:
    lease = "timestamp() + $off" if lease_offset_ms is not None else "null"
    q(
        pool,
        ops,
        "CREATE (:Task {key: $key, kind: 'triage_finding', role: 'freshness', status: $status, attempts: $att, "
        f"finding_key: $key, lease_until_ms: {lease}, payload_json: '{{}}'}})",
        key=key,
        status=status,
        att=attempts,
        off=lease_offset_ms,
    )


def test_done_and_failed_tasks_are_never_claimed_even_with_an_expired_lease(
    pool: FalkorPool, graphs: tuple[str, str]
) -> None:
    ops, _ = graphs
    add_task(pool, ops, "t-done", "done", 1, -10_000)
    add_task(pool, ops, "t-failed", "failed", 1, -10_000)
    assert co.claim(pool, "freshness", ops) is None


def test_three_tasks_and_twenty_claimers_give_exactly_three_claims(pool: FalkorPool, graphs: tuple[str, str]) -> None:
    ops, _ = graphs
    for n in range(3):
        add_task(pool, ops, f"t-{n}", "queued")
    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(lambda _: co.claim(pool, "freshness", ops), range(20)))
    claimed = [r for r in results if r is not None]
    assert sorted(t.key for t in claimed) == ["t-0", "t-1", "t-2"]
    assert q(pool, ops, "MATCH (:Agent)-[c:CLAIMED]->(:Task) RETURN count(c)")[0][0] == 3
    assert q(pool, ops, "MATCH (t:Task) WHERE t.status = 'running' RETURN count(t)")[0][0] == 3


def test_live_lease_blocks_a_second_claim_and_an_expired_one_fences_the_first_claimer(
    pool: FalkorPool, graphs: tuple[str, str]
) -> None:
    ops, _ = graphs
    add_task(pool, ops, "t-1", "queued")
    first = co.claim(pool, "freshness", ops)
    assert first is not None and first.attempt == 1
    assert co.claim(pool, "freshness", ops) is None
    assert co.heartbeat(pool, first, ops) is True

    q(pool, ops, "MATCH (t:Task {key: 't-1'}) SET t.lease_until_ms = timestamp() - 1")
    second = co.claim(pool, "freshness", ops)
    assert second is not None and second.attempt == 2
    assert co.heartbeat(pool, first, ops) is False
    assert co.complete(pool, first, {"by": "first"}, graph=ops) is False
    assert co.handoff(pool, first, "action", "draft_stale_issue", "late", {}, ops) is None
    assert co.complete(pool, second, {"by": "second"}, graph=ops) is True
    row = q(pool, ops, "MATCH (t:Task {key: 't-1'}) RETURN t.status, t.result_json, t.lease_until_ms")[0]
    assert row == ["done", json.dumps({"by": "second"}), None]


def test_exhausted_expired_task_is_reaped_not_reclaimed(pool: FalkorPool, graphs: tuple[str, str]) -> None:
    ops, _ = graphs
    add_task(pool, ops, "t-1", "running", co.MAX_ATTEMPTS, -1_000)
    assert co.claim(pool, "freshness", ops) is None
    assert co.reap(pool, ops) == 1
    assert q(pool, ops, "MATCH (t:Task {key: 't-1'}) RETURN t.status, t.error")[0] == ["failed", "lease_expired"]


def test_enqueue_is_deduplicated_per_kind_and_finding(pool: FalkorPool, graphs: tuple[str, str]) -> None:
    ops, _ = graphs
    assert co.enqueue_task(pool, "triage_finding", "freshness", FINDING, graph=ops) is not None
    assert co.enqueue_task(pool, "triage_finding", "freshness", FINDING, graph=ops) is None
    assert co.enqueue_task(pool, "draft_stale_issue", "action", FINDING, graph=ops) is not None


def test_finding_journey_triage_then_draft_then_verify(
    pool: FalkorPool, graphs: tuple[str, str], settings: Settings
) -> None:
    ops, kep = graphs
    llm = FakeLlm()
    summary = co.run_coordination_tick(settings, llm=llm, pool=pool, kep_graph=kep, ops_graph=ops)
    assert summary["enqueued"] == {"triage_finding": 1, "draft_stale_issue": 0}
    assert summary["processed"] == {
        "freshness": {"handed_off": 1},
        "action": {"handed_off": 1},
        "verifier": {"done": 1},
    }

    f = q(
        pool,
        kep,
        "MATCH (f:Finding) RETURN f.state, f.triage_verdict, f.triage_model, f.action_draft_key, f.assessment",
    )[0]
    assert f[:3] == ["drafted", "confirmed", "fake-model"] and f[3] is not None and "[" in f[4]
    draft = q(pool, ops, "MATCH (d:ActionDraft) RETURN d.key, d.status, d.body, d.finding_key")[0]
    assert draft[0] == f[3] and draft[1] == "verified" and draft[3] == FINDING
    assert A_URL in draft[2] and B_URL in draft[2] and "https://example.com" not in draft[2]
    handoffs = q(pool, ops, "MATCH (h:Handoff) RETURN h.from_role, h.to_role")
    assert sorted(handoffs) == [["action", "verifier"], ["freshness", "action"]]
    assert q(pool, ops, "MATCH (:Task)-[p:PRODUCED]->(:ActionDraft) RETURN count(p)")[0][0] == 1
    assert q(pool, ops, "MATCH (t:Task) RETURN t.status, t.kind")[0] == ["done", "verify_draft"]

    again = co.run_coordination_tick(settings, llm=llm, pool=pool, kep_graph=kep, ops_graph=ops)
    assert again["enqueued"] == {"triage_finding": 0, "draft_stale_issue": 0} and llm.calls == 1


def test_needs_human_verdict_is_triaged_and_not_drafted(
    pool: FalkorPool, graphs: tuple[str, str], settings: Settings
) -> None:
    ops, kep = graphs
    co.run_coordination_tick(settings, llm=FakeLlm("needs_human"), pool=pool, kep_graph=kep, ops_graph=ops)
    assert q(pool, kep, "MATCH (f:Finding) RETURN f.state, f.triage_verdict")[0] == ["triaged", "needs_human"]
    assert q(pool, ops, "MATCH (d:ActionDraft) RETURN count(d)")[0][0] == 0


def test_answer_citing_an_unknown_id_is_discarded_and_the_finding_stays_open(
    pool: FalkorPool, graphs: tuple[str, str], settings: Settings
) -> None:
    ops, kep = graphs
    out = run_freshness_once(settings, llm=FakeLlm("bad_citation"), pool=pool, kep_graph=kep, ops_graph=ops)
    assert out["counts"] == {"rejected": 1}
    assert q(pool, kep, "MATCH (f:Finding) RETURN f.state, f.assessment, f.triage_verdict")[0] == ["open", None, None]

    co.run_coordination_tick(settings, llm=FakeLlm("bad_citation"), pool=pool, kep_graph=kep, ops_graph=ops)
    assert q(pool, ops, "MATCH (t:Task) RETURN t.status")[0][0] == "failed"
    assert q(pool, kep, "MATCH (f:Finding) RETURN f.state")[0][0] == "open"


def test_daily_spend_cap_stops_the_agent(pool: FalkorPool, graphs: tuple[str, str]) -> None:
    ops, kep = graphs
    capped = Settings(_env_file=None, findings_agent_daily_usd=0.0)  # type: ignore[call-arg]
    llm = FakeLlm()
    out = run_freshness_once(capped, llm=llm, pool=pool, kep_graph=kep, ops_graph=ops)
    assert out["stopped"] == "daily_cap_reached" and out["attempted"] == 0 and llm.calls == 0

    tiny = Settings(_env_file=None, findings_agent_daily_usd=0.001)  # type: ignore[call-arg]
    out = run_freshness_once(tiny, llm=llm, pool=pool, kep_graph=kep, ops_graph=ops)
    assert out["counts"] == {"triaged": 1}
    assert q(pool, ops, "MATCH (b:BudgetDay) RETURN b.spent_usd_micros")[0][0] > 0


async def test_board_reads_agents_tasks_handoffs_and_drafts(
    pool: FalkorPool, graphs: tuple[str, str], settings: Settings
) -> None:
    ops, kep = graphs
    co.run_coordination_tick(settings, llm=FakeLlm(), pool=pool, kep_graph=kep, ops_graph=ops)
    board = await co.board(pool, ops, kep)
    assert {a["name"] for a in board["agents"]} == {"freshness", "action", "verifier"}
    assert board["tasks"][0]["finding_key"] == FINDING
    assert len(board["handoffs_last_hour"]) == 2 and board["drafts"][0]["status"] == "verified"
    assert board["findings_recent"][0]["state"] == "drafted"
