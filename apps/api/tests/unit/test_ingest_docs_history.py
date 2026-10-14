"""Field-level history diff and status-change chains (03 §7.2)."""

from __future__ import annotations

from app.ingest.common import Revision, _same_document
from app.ingest.history import _chain, _changes_for_kep, parse_pr_number
from app.ingest.kep_yaml import parse_kep_yaml
from app.schema.labels import VALID_TO_OPEN


def _rev(sha: str, at: int, text: str) -> tuple[Revision, dict[str, str | None], dict[str, str | None]]:
    meta = parse_kep_yaml(text)
    return Revision(sha=sha, at=at, subject="s", path="keps/sig-x/1-k/kep.yaml"), meta.field_values(), meta.raw_values()


def test_pr_number_parsing() -> None:
    assert parse_pr_number("Merge pull request #5761 from user/branch") == 5761
    assert parse_pr_number("KEP-1287: graduate to GA (#5562)") == 5562
    assert parse_pr_number("mark in-place pod resize as implemented") is None


def test_same_document_rule() -> None:
    assert _same_document("keps/sig-network/1797-fqdn/kep.yaml", "keps/sig-node/1797-fqdn/kep.yaml")
    assert _same_document("keps/sig-node/1287-old-name/kep.yaml", "keps/sig-node/1287-new-name/kep.yaml")
    assert not _same_document("keps/sig-apps/3850-backoff/kep.yaml", "keps/sig-scheduling/5055-taints/kep.yaml")


def test_changes_chain_and_reversal() -> None:
    revs = [
        _rev("a" * 40, 100, "status: implementable\nstage: alpha\n"),
        _rev("b" * 40, 200, "status: implementable\nstage: beta\n"),
        _rev("c" * 40, 150, "status: implementable\nstage: alpha\n"),  # author date earlier than parent
        _rev("d" * 40, 400, "status: imlpemented\nstage: alpha\n"),
    ]
    rows = _changes_for_kep("keps/sig-x/1-k", revs)
    previous = _chain(rows)
    stage = [r for r in rows if r["field"] == "stage"]
    status = [r for r in rows if r["field"] == "status"]
    assert [(r["from_value"], r["to_value"], r["seq"]) for r in stage] == [
        (None, "alpha", 1),
        ("alpha", "beta", 2),
        ("beta", "alpha", 3),
    ]
    assert [r["is_reversal"] for r in stage] == [False, False, True]
    assert stage[2]["at"] == 150 and stage[2]["valid_from"] == 200  # clamped, never before its predecessor
    assert stage[1]["valid_to"] == stage[2]["valid_from"]
    assert stage[2]["valid_to"] == VALID_TO_OPEN
    assert [(r["to_value"], r["to_raw"]) for r in status] == [
        ("implementable", "implementable"),
        ("implemented", "imlpemented"),
    ]
    assert stage[0]["key"] == f"sc:keps/sig-x/1-k:stage:{'a' * 40}"
    assert (stage[1]["key"], stage[0]["key"]) in previous
