"""The five predicates and the Finding lifecycle against a throwaway FalkorDB graph."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from ulid import ULID

from app.db.batch import BatchWriter
from app.db.falkordb import FalkorPool, Role
from app.ingest.findings import detect_findings
from app.schema.labels import VALID_TO_OPEN
from app.settings import Settings

ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
T0 = 1_600_000_000


def _pool() -> FalkorPool:
    settings = Settings(_env_file=ENV_FILE if ENV_FILE.exists() else None)  # type: ignore[call-arg]
    pool = FalkorPool(settings)
    try:
        pool.list_graphs()
    except Exception as exc:  # noqa: BLE001 - any connection problem skips the integration test
        pytest.skip(f"FalkorDB not reachable: {exc}")
    return pool


@pytest.fixture()
def writer() -> Iterator[BatchWriter]:
    pool = _pool()
    name = f"test_findings_{ULID()}".lower()
    w = BatchWriter(pool, name, "test")
    try:
        yield w
    finally:
        pool.graph(Role.WRITER, name).delete()
        pool.close()


def kep(
    n: int, sig: str, slug: str, status: str, stage: str | None = None, latest: str | None = None
) -> dict[str, Any]:
    key = f"keps/{sig}/{n}-{slug}"
    return {
        "key": key,
        "number": n,
        "title": slug,
        "status": status,
        "stage": stage,
        "latest_milestone": latest,
        "owning_sig": sig,
        "stub": False,
        "url": f"https://github.com/kubernetes/enhancements/tree/x/{key}",
        "source_url": f"https://github.com/kubernetes/enhancements/blob/x/{key}/kep.yaml",
    }


def issue(n: int, state: str, reason: str | None = None) -> dict[str, Any]:
    url = f"https://github.com/kubernetes/enhancements/issues/{n}"
    return {"key": f"kubernetes/enhancements#{n}", "number": n, "state": state, "state_reason": reason, "url": url,
            "source_url": url, "closed_at_iso": "2019-09-09T21:03:18Z" if state == "closed" else None}  # fmt: skip


def state(valid_to: int = VALID_TO_OPEN, **extra: Any) -> dict[str, Any]:
    return {"valid_from": T0, "valid_to": valid_to, "source_url": "https://github.com/x", **extra}


def build(w: BatchWriter) -> dict[str, str]:
    keps = {
        "583": kep(583, "sig-scheduling", "coscheduling", "provisional"),
        "4671": kep(4671, "sig-scheduling", "gang-scheduling", "implementable", "stable", "v1.38"),
        "5978": kep(5978, "sig-node", "cluster-resource-claim-template", "withdrawn", "alpha", "v1.37"),
        "1923": kep(1923, "sig-scheduling", "prefer-nominated-node", "implemented", "stable", "v1.24"),
        "961": kep(961, "sig-apps", "maxunavailable-for-statefulset", "implementable", "alpha", "v1.37"),
        "100": kep(100, "sig-node", "no-stage-labels", "implemented", "stable", None),
        "200": kep(200, "sig-node", "old-tracking", "provisional"),
        "300": kep(300, "sig-apps", "successor", "implemented"),
        "301": kep(301, "sig-apps", "predecessor", "replaced"),
    }
    w.upsert_nodes("KEP", list(keps.values()))
    w.upsert_nodes(
        "Release",
        [{"key": f"v1.{m}", "minor": m, "ordinal": m, "is_future": m > 37} for m in (22, 24, 37, 38, 39)],
    )
    w.upsert_nodes(
        "Issue",
        [issue(583, "closed", "completed"), issue(4671, "open"), issue(1923, "closed", "completed"),
         issue(961, "open"), issue(100, "closed", "completed"), issue(200, "closed", "not_planned"),
         issue(5978, "closed", "not_planned")],
        extra_labels=["Ticket"],
    )  # fmt: skip
    w.upsert_nodes("Label", [{"key": x, "name": x} for x in ("stage/stable", "stage/beta", "tracked/yes")])
    w.upsert_nodes(
        "Document",
        [{"key": f"kubernetes/enhancements:{k['key']}/kep.yaml", "kind": "kep_yaml",
          "url": f"https://github.com/kubernetes/enhancements/blob/pin/{k['key']}/kep.yaml"} for k in keps.values()],
    )  # fmt: skip
    w.upsert_edges(
        "HAS_DOCUMENT",
        "KEP",
        "Document",
        [{"from": k["key"], "to": f"kubernetes/enhancements:{k['key']}/kep.yaml", "props": {"role": "metadata"}}
         for k in keps.values()],
    )  # fmt: skip
    tracked = [(n, VALID_TO_OPEN) for n in ("583", "4671", "1923", "961", "100", "5978")] + [
        ("200", T0 + 10)
    ]  # closed interval: not current state
    w.upsert_edges(
        "TRACKED_BY",
        "KEP",
        "Issue",
        [{"from": keps[n]["key"], "to": f"kubernetes/enhancements#{n}", "props": state(vt)} for n, vt in tracked],
    )
    w.upsert_edges(
        "LABELED",
        "Issue",
        "Label",
        [
            {"from": "kubernetes/enhancements#4671", "to": "stage/stable", "props": state()},
            {"from": "kubernetes/enhancements#1923", "to": "stage/beta", "props": state()},
            {"from": "kubernetes/enhancements#1923", "to": "stage/stable", "props": state(T0 + 5)},  # removed
        ],
    )
    w.upsert_edges(
        "MILESTONED",
        "Issue",
        "Release",
        [
            {"from": "kubernetes/enhancements#4671", "to": "v1.38", "props": state()},
            {"from": "kubernetes/enhancements#1923", "to": "v1.22", "props": state()},
            {"from": "kubernetes/enhancements#961", "to": "v1.39", "props": state()},
        ],
    )
    w.upsert_edges(
        "LATEST",
        "KEP",
        "Release",
        [
            {"from": keps[n]["key"], "to": keps[n]["latest_milestone"], "props": state()}
            for n in ("4671", "5978", "1923", "961")
        ],
    )
    w.upsert_edges(
        "TARGETS",
        "KEP",
        "Release",
        [
            {"from": keps["5978"]["key"], "to": "v1.37", "props": state(stage="alpha")},
            {"from": keps["5978"]["key"], "to": "v1.38", "props": state(stage="beta")},
        ],
        identity=["stage"],
    )
    w.upsert_edges(
        "REPLACES",
        "KEP",
        "KEP",
        [
            {"from": keps["4671"]["key"], "to": keps["583"]["key"], "props": state(declared_by="successor")},
            {"from": keps["300"]["key"], "to": keps["301"]["key"], "props": state(declared_by="both")},
        ],
    )
    w.upsert_edges(
        "SUPERSEDED_BY",
        "KEP",
        "KEP",
        [
            {"from": keps["583"]["key"], "to": keps["4671"]["key"], "props": state(derived=True)},
            {"from": keps["301"]["key"], "to": keps["300"]["key"], "props": state(derived=False)},
        ],
    )
    return {n: k["key"] for n, k in keps.items()}


def _findings(w: BatchWriter) -> dict[str, dict[str, Any]]:
    rows = w.query("MATCH (f:Finding) RETURN f.key, properties(f)")
    return {str(r[0]): r[1] for r in rows}


def test_predicates_and_lifecycle(writer: BatchWriter) -> None:
    keys = build(writer)
    result = detect_findings(writer)
    assert result["by_kind"] == {
        "active_status_closed_issue": 1,
        "terminal_status_future_targets": 1,
        "one_sided_replacement": 1,
        "stage_mismatch": 1,
        "milestone_mismatch": 2,
    }
    found = _findings(writer)
    active = found[f"fnd:active_status_closed_issue:{keys['583']}"]
    # Closed 2019-09-09: before GitHub recorded close reasons, so the "completed" is a backfill (findings.py).
    assert active["state"] == "open" and active["suggested_fix"] == "review_status"
    assert active["b_value"] == "closed (reason not recorded) on 2019-09-09"
    assert active["a_value"] == "provisional" and active["b_url"].endswith("/issues/583")
    assert active["a_url"].endswith(f"{keys['583']}/kep.yaml")
    assert f"fnd:one_sided_replacement:{keys['583']}:{keys['4671']}" in found
    assert found[f"fnd:terminal_status_future_targets:{keys['5978']}"]["b_value"] == "milestone.beta = v1.38"
    assert found[f"fnd:stage_mismatch:{keys['1923']}"]["b_value"] == "stage/beta"
    assert f"fnd:milestone_mismatch:{keys['961']}" in found
    ev = writer.query(
        "MATCH (f:Finding {key: $k})-[e:EVIDENCED_BY]->(n) RETURN e.evidence_kind ORDER BY e.evidence_kind",
        {"k": f"fnd:active_status_closed_issue:{keys['583']}"},
    )
    assert [r[0] for r in ev] == ["kep_yaml", "tracking_issue"]
    about = writer.query("MATCH (f:Finding)-[:ABOUT]->(k:KEP) RETURN count(f)")
    assert about[0][0] == 6

    # triage fields survive a re-run; the predicate stops holding -> resolved_upstream
    fkey = f"fnd:active_status_closed_issue:{keys['583']}"
    writer.query("MATCH (f:Finding {key: $k}) SET f.triage_verdict = 'confirmed', f.state = 'triaged'", {"k": fkey})
    writer.query("MATCH (k:KEP {key: $k}) SET k.status = 'implemented'", {"k": keys["583"]})
    second = detect_findings(writer)
    assert second["resolved"] == 1
    f = _findings(writer)[fkey]
    assert f["state"] == "resolved_upstream" and f["triage_verdict"] == "confirmed"

    # recurrence reopens the same node
    writer.query("MATCH (k:KEP {key: $k}) SET k.status = 'provisional'", {"k": keys["583"]})
    third = detect_findings(writer)
    assert third["reopened"] == 1
    f = _findings(writer)[fkey]
    assert f["state"] == "open" and f["reopened_count"] == 1 and f["triage_verdict"] == "confirmed"
