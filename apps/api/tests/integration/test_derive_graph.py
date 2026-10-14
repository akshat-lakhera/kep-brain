"""Decision derivation against a throwaway graph shaped like DEC-01 (KEP-1287 -> PR #5761)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ulid import ULID

from app.db.batch import BatchWriter
from app.db.falkordb import FalkorPool, Role
from app.ingest.derive import derive_decisions
from app.schema.labels import VALID_TO_OPEN
from app.settings import Settings

ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
KEP = "keps/sig-node/1287-in-place-update-pod-resources"
SHA = "d47a8df46c8c26d6300fd30047520e397127805c"
PR = "kubernetes/enhancements#5761"
MERGED = 1768531528


@pytest.fixture()
def writer() -> Iterator[BatchWriter]:
    settings = Settings(_env_file=ENV_FILE if ENV_FILE.exists() else None)  # type: ignore[call-arg]
    pool = FalkorPool(settings)
    try:
        pool.list_graphs()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"FalkorDB not reachable: {exc}")
    name = f"test_derive_{ULID()}".lower()
    w = BatchWriter(pool, name, "test")
    try:
        yield w
    finally:
        pool.graph(Role.WRITER, name).delete()
        pool.close()


def test_dec01_trace(writer: BatchWriter) -> None:
    w = writer
    w.upsert_nodes("KEP", [{"key": KEP, "number": 1287, "status": "implemented"}])
    w.upsert_nodes(
        "Person",
        [{"key": x, "login": x, "is_bot": x == "k8s-ci-robot"}
         for x in ("sergeykanzhelev", "mrunalp", "tallclair", "natasha41575", "k8s-ci-robot", "dchen1107")],
    )  # fmt: skip
    sc = f"sc:{KEP}:status:{SHA}"
    w.upsert_nodes(
        "StatusChange",
        [{"key": sc, "kind": "metadata", "field": "status", "from_value": "implementable", "to_value": "implemented",
          "at": 1767035207, "is_reversal": False, "valid_to": VALID_TO_OPEN,
          "source_url": f"https://github.com/kubernetes/enhancements/blob/{SHA}/{KEP}/kep.yaml"}],
    )  # fmt: skip
    w.upsert_nodes(
        "Commit",
        [{"key": f"kubernetes/enhancements@{SHA}", "sha": SHA, "authored_at": 1767035207, "pr_number": 5761,
          "url": f"https://github.com/kubernetes/enhancements/commit/{SHA}"}],
    )  # fmt: skip
    w.upsert_nodes(
        "PullRequest",
        [{"key": PR, "number": 5761, "merged_at": MERGED, "merged_by_login": "k8s-ci-robot",
          "author_login": "natasha41575", "url": "https://github.com/kubernetes/enhancements/pull/5761"}],
    )  # fmt: skip
    w.upsert_nodes(
        "Review",
        [{"key": "rv1", "state": "APPROVED", "author_login": "sergeykanzhelev", "submitted_at": MERGED - 100,
          "commands": ["/lgtm", "/approve"], "url": "https://github.com/kubernetes/enhancements/pull/5761#r1"},
         {"key": "rv2", "state": "APPROVED", "author_login": "mrunalp", "submitted_at": MERGED - 50,
          "commands": [], "url": "https://github.com/kubernetes/enhancements/pull/5761#r2"}],
    )  # fmt: skip
    w.upsert_nodes(
        "Comment",
        [{"key": "cm1", "author_login": "tallclair", "created_at": MERGED - 900, "commands": ["/lgtm"],
          "url": "https://github.com/kubernetes/enhancements/pull/5761#c1"}],
    )  # fmt: skip
    w.upsert_edges("CHANGED", "KEP", "StatusChange", [{"from": KEP, "to": sc, "props": {}}])
    w.upsert_edges(
        "IN_COMMIT", "StatusChange", "Commit", [{"from": sc, "to": f"kubernetes/enhancements@{SHA}", "props": {}}]
    )
    w.upsert_edges(
        "IN_PR", "Commit", "PullRequest", [{"from": f"kubernetes/enhancements@{SHA}", "to": PR, "props": {}}]
    )
    w.upsert_edges("ON", "Review", "PullRequest", [{"from": r, "to": PR, "props": {}} for r in ("rv1", "rv2")])
    w.upsert_edges("ON", "Comment", "PullRequest", [{"from": "cm1", "to": PR, "props": {}}])
    # a replacement and a PRR approval
    w.upsert_nodes("KEP", [{"key": "keps/sig-node/1-old", "number": 1}])
    w.upsert_edges(
        "REPLACES", "KEP", "KEP",
        [{"from": KEP, "to": "keps/sig-node/1-old", "props": {"valid_from": 1000, "valid_to": VALID_TO_OPEN,
          "source_url": f"https://github.com/kubernetes/enhancements/blob/{SHA}/{KEP}/kep.yaml"}}],
    )  # fmt: skip
    w.upsert_edges(
        "APPROVES", "Person", "KEP",
        [{"from": "dchen1107", "to": KEP, "props": {"valid_from": 500, "valid_to": VALID_TO_OPEN}}],
    )  # fmt: skip
    w.upsert_edges(
        "PRR_APPROVED", "Person", "KEP",
        [{"from": "dchen1107", "to": KEP, "props": {"stage": "beta", "valid_from": 2000, "valid_to": VALID_TO_OPEN,
          "source_url": f"https://github.com/kubernetes/enhancements/blob/{SHA}/keps/prod-readiness/sig-node/1287.yaml"}}],
        identity=["stage"],
    )  # fmt: skip

    counts = derive_decisions(w)
    assert counts["status_transition"] == 1 and counts["replacement"] == 1 and counts["prr_approval"] == 1

    dkey = f"dec:status_transition:{KEP}:{SHA}"
    rows = w.query(
        "MATCH (d:Decision {key: $k})-[e:DECIDED_BY]->(p:Person) RETURN p.key, e.role ORDER BY p.key, e.role",
        {"k": dkey},
    )
    roles = {(r[0], r[1]) for r in rows}
    assert {("sergeykanzhelev", "approver"), ("mrunalp", "approver"), ("tallclair", "lgtm"),
            ("k8s-ci-robot", "merger"), ("natasha41575", "author")} <= roles  # fmt: skip
    ev = w.query(
        "MATCH (d:Decision {key: $k})-[e:EVIDENCED_BY]->(n) RETURN e.evidence_kind ORDER BY e.evidence_kind",
        {"k": dkey},
    )
    assert [r[0] for r in ev] == ["command_comment", "commit", "pr", "review", "review", "status_change"]
    d = w.query(
        "MATCH (d:Decision {key: $k})-[:ABOUT]->(k:KEP) RETURN d.decided_at, d.human_decider, d.url", {"k": dkey}
    )
    assert d[0] == [MERGED, True, "https://github.com/kubernetes/enhancements/pull/5761"]
    rep = w.query("MATCH (d:Decision {kind: 'replacement'})-[e:DECIDED_BY]->(p) RETURN p.key, e.role, d.summary")
    assert rep[0][:2] == ["dchen1107", "approver"]
    assert rep[0][2] == "KEP-1287 declared that it replaces KEP-1 on 1970-01-01, approved by dchen1107."
    # idempotent
    derive_decisions(w)
    assert w.query("MATCH (d:Decision) RETURN count(d)")[0][0] == 3
