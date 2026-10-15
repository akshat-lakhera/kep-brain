# ruff: noqa: E501
"""Person, SIG and changes routes against a throwaway fixture graph (the shared fixture plus leadership,
releases and one issue milestone event)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fixture_graph import GH, OPEN, STATEMENTS

from app.api import audit_check
from app.db.falkordb import FalkorPool, Role
from app.main import create_app
from app.settings import Settings

GRAPH = "test_api2_routes"
SIGS_YAML = "https://github.com/kubernetes/community/blob/53c338ecba4a2a9240f6654cca1d6a9dac25c785/sigs.yaml"
FINDING = "fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling"

EXTRA = [
    f"""
MATCH (ss:SIG {{key: 'sig-scheduling'}}), (sol:Person {{key: 'soltysh'}}), (k1287:KEP {{number: 1287}})
SET ss.in_scope = true, ss.mission = 'Scheduling of pods'
CREATE (sol)-[:CHAIRS {{valid_from: 0, valid_from_iso: '2026-10-14T19:09:13Z', valid_to: {OPEN}, source_url: '{SIGS_YAML}'}}]->(ss),
 (:Release {{key: 'v1.35', name: 'v1.35', ordinal: 35, is_future: false, released_at: 1766001715, first_seen_at: 1792004953}}),
 (:Release {{key: 'v1.36', name: 'v1.36', ordinal: 36, is_future: false, released_at: 1776880634}}),
 (:Release {{key: 'v1.37', name: 'v1.37', ordinal: 37, is_future: true}}),
 (i1287:Issue:Ticket {{key: 'kubernetes/enhancements#1287', number: 1287, state: 'open', url: '{GH}/issues/1287'}}),
 (k1287)-[:TRACKED_BY {{valid_from: 0, valid_to: {OPEN}, source_url: 'x'}}]->(i1287),
 (i1287)-[:HAS_EVENT]->(m:StatusChange {{key: 'ghe:m1', kind: 'milestone', kep_path: k1287.key, field: 'milestone',
   op: 'milestoned', to_value: 'v1.36', at: 1766000000, at_iso: '2025-12-17T19:33:20Z', actor_login: 'soltysh',
   seq: 1, source_url: '{GH}/issues/1287'}}),
 (k1287)-[:CHANGED]->(m)
""",
]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    pool = FalkorPool(Settings())
    try:
        graphs = pool.list_graphs()
    except Exception:  # noqa: BLE001
        pytest.skip("FalkorDB not reachable")
    if GRAPH in graphs:
        pool.graph(Role.WRITER, GRAPH).delete()
    for stmt in [*STATEMENTS, *EXTRA]:
        pool.run_sync(Role.WRITER, GRAPH, stmt, read_only=False, timeout_ms=10000)
    evals = tmp_path_factory.mktemp("evals")
    (evals / "audit-check.yaml").write_text(
        f"findings:\n  - key: {FINDING}\n    verdict: correct\n    checked_by: team member (data)\n"
        "    checked_at: 2026-10-16\n    note: issue 583 closed, kep.yaml provisional\n",
        encoding="utf-8",
    )
    mp = pytest.MonkeyPatch()
    mp.setenv("EVALS_DIR", str(Path(evals)))
    audit_check._cache.clear()
    try:
        with TestClient(create_app()) as c:
            c.app.state.kep_graph = GRAPH  # type: ignore[attr-defined]
            yield c
    finally:
        mp.undo()
        pool.graph(Role.WRITER, GRAPH).delete()
        pool.close()


def test_person_page(client: TestClient) -> None:
    body = client.get("/v1/people/SolTysh").json()
    assert body["login"] == "soltysh" and body["url"] == "https://github.com/soltysh" and body["is_bot"] is False
    assert body["roles"] == [
        {"org": "sig-scheduling", "org_kind": "SIG", "role": "chair", "valid_from_iso": "2026-10-14T19:09:13Z",
         "source_url": SIGS_YAML},
    ]  # fmt: skip
    prr = body["keps"]["prr_approved"]
    assert [(p["stage"], p["kep"]["number"]) for p in prr] == [("alpha", 4671)]
    assert set(prr[0]["kep"]) == {"key", "number", "title", "owning_sig", "status", "stage", "latest_milestone",
                                  "url", "open_findings"}  # fmt: skip
    assert body["keps"]["authored"] == [] and body["owners"] == [] and body["decisions"] == []
    assert body["connectivity"]["rank"] == 2 and body["connectivity"]["of"] == 2
    assert "algo.pageRank(null, 'DECIDED_BY')" in body["connectivity"]["method"]


def test_person_decisions_and_bot(client: TestClient) -> None:
    body = client.get("/v1/people/natasha41575").json()
    assert body["decisions"] == [
        {
            "key": "dec:status_transition:keps/sig-node/1287-in-place-update-pod-resources:d47a8df46c",
            "kind": "status_transition",
            "summary": "status implementable -> implemented",
            "kep_number": 1287,
            "kep_title": "In-place Update of Pod Resources",
            "decided_at_iso": "2026-01-16T02:45:28Z",
            "url": f"{GH}/pull/5761",
            "role": "author",
        }
    ]
    assert body["connectivity"]["rank"] == 1
    bot = client.get("/v1/people/k8s-ci-robot").json()
    assert bot["is_bot"] is True and bot["connectivity"] is None
    assert [k["number"] for k in bot["keps"]["approves"]] == [4671]


def test_unknown_person_is_404(client: TestClient) -> None:
    res = client.get("/v1/people/no-such-login")
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"


def test_sig_list_and_page(client: TestClient) -> None:
    items = client.get("/v1/sigs").json()["items"]
    assert [i["key"] for i in items] == ["sig-scheduling", "sig-apps", "sig-node"]
    sched = items[0]
    assert sched["in_scope"] is True and sched["keps"] == 3 and sched["open_findings"] == 1
    assert sched["chairs"] == [{"login": "soltysh", "url": "https://github.com/soltysh"}] and sched["tech_leads"] == []
    page = client.get("/v1/sigs/sig-scheduling").json()
    assert page["keps_by_status"] == {"implementable": 2, "provisional": 1}
    assert [k["number"] for k in page["keps"]] == [583, 4671, 5832]
    assert page["people"][0] == {
        "login": "soltysh",
        "url": "https://github.com/soltysh",
        "roles": ["chair", "prr_approver"],
    }
    assert "k8s-ci-robot" not in {p["login"] for p in page["people"]}
    assert page["subprojects"] == []
    assert [f["key"] for f in page["findings"]] == [FINDING]
    assert page["findings"][0]["human_verdict"] == {
        "verdict": "correct", "checked_by": "team member (data)", "checked_at": "2026-10-16",
        "note": "issue 583 closed, kep.yaml provisional",
    }  # fmt: skip
    assert client.get("/v1/sigs/sig-nope").status_code == 404


def test_changes_since_release(client: TestClient) -> None:
    body = client.get("/v1/changes").json()
    assert body["since"] == "v1.36" and body["releases"] == ["v1.35", "v1.36", "v1.37"]
    assert body["window"] == {"start_iso": "2025-12-17T19:33:20Z", "basis": "tracking_issue_milestone"}
    assert body["counts"] == {"keps_changed": 1, "status_transitions": 1, "stage_changes": 0, "milestone_changes": 1, "label_changes": 0,
                              "new_keps": 1}  # fmt: skip
    status, milestone = body["items"]
    assert status == {
        "kep_number": 1287, "kep_title": "In-place Update of Pod Resources", "owning_sig": "sig-node",
        "kind": "metadata", "field": "status", "from_value": "implementable", "to_value": "implemented",
        "at_iso": "2025-12-29T00:00:00Z", "actor_login": "natasha41575",
        "pr": {"number": 5761, "url": f"{GH}/pull/5761"}, "source_url": f"{GH}/commit/d47a8df46c",
    }  # fmt: skip
    assert milestone["kind"] == "milestone" and milestone["to_value"] == "v1.36" and milestone["pr"] is None
    assert client.get("/v1/changes", params={"sig": "sig-apps"}).json()["items"] == []


def test_changes_window_fallbacks_and_404(client: TestClient) -> None:
    v135 = client.get("/v1/changes", params={"since": "1.35"}).json()
    assert v135["since"] == "v1.35" and v135["window"]["basis"] == "release_first_seen" and v135["items"] == []
    assert client.get("/v1/changes", params={"since": "v1.37"}).status_code == 404
    res = client.get("/v1/changes", params={"since": "v1.99"})
    assert res.status_code == 404 and res.json()["error"]["details"]["releases"] == ["v1.35", "v1.36", "v1.37"]
