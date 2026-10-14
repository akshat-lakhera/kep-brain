"""Ticket-layer parsing: Prow commands, milestones, timeline chains and reversals."""

from __future__ import annotations

from typing import Any

from app.ingest.tickets import (
    build_timeline_changes,
    label_valid_from,
    milestone_valid_from,
    parse_commands,
    release_key,
    scrub,
)
from app.schema.labels import VALID_TO_OPEN


def _lab(i: int, typename: str, name: str, at: str, actor: str = "someone") -> dict[str, Any]:
    return {"__typename": typename, "id": f"E{i}", "createdAt": at, "actor": {"login": actor}, "label": {"name": name}}


def _ms(i: int, typename: str, title: str, at: str) -> dict[str, Any]:
    return {
        "__typename": typename,
        "id": f"M{i}",
        "createdAt": at,
        "actor": {"login": "k8s-ci-robot"},
        "milestoneTitle": title,
    }


def test_parse_commands_own_line_only() -> None:
    assert parse_commands("/lgtm\r\n/approve") == ["/lgtm", "/approve"]
    assert parse_commands("LGTM, thanks") == []
    assert parse_commands("approvers can write `/approve` in a comment") == []
    assert parse_commands("  /approve cancel\n/hold") == ["/approve cancel", "/hold"]
    assert parse_commands(None) == []


def test_release_key_normalises() -> None:
    assert release_key("v1.31") == "v1.31"
    assert release_key("1.31") == "v1.31"
    assert release_key("keps-beta") is None
    assert release_key(None) is None


def test_scrub_removes_email() -> None:
    assert scrub("ping jane.doe@example.com please") == "ping [email removed] please"


def test_stage_reversal_matches_kep_1287() -> None:
    events = [
        _lab(1, "LabeledEvent", "stage/beta", "2024-06-04T00:45:00Z", "k8s-ci-robot"),
        _lab(2, "UnlabeledEvent", "stage/beta", "2025-06-09T00:44:00Z", "fykaa"),
        _lab(3, "LabeledEvent", "stage/stable", "2025-06-09T00:44:30Z", "fykaa"),
        _lab(4, "UnlabeledEvent", "stage/stable", "2025-06-09T00:54:00Z", "fykaa"),
        _lab(5, "LabeledEvent", "stage/beta", "2025-06-09T00:54:09Z", "fykaa"),
        _lab(6, "LabeledEvent", "stage/stable", "2026-01-15T22:47:27Z", "k8s-ci-robot"),
    ]
    changes = build_timeline_changes(events)
    reversals = [(c.field, c.op) for c in changes if c.is_reversal]
    assert reversals == [("stage/beta", "added")]
    by_key = {c.key: c for c in changes}
    assert by_key["ghe:E1"].kind == "label" and by_key["ghe:E1"].to_value == "stage/beta"
    assert by_key["ghe:E2"].op == "removed" and by_key["ghe:E2"].from_value == "stage/beta"


def test_chain_per_field_seq_valid_to_previous() -> None:
    events = [
        _lab(2, "UnlabeledEvent", "lifecycle/stale", "2024-02-01T00:00:00Z"),
        _lab(1, "LabeledEvent", "lifecycle/stale", "2024-01-01T00:00:00Z"),
        _lab(3, "LabeledEvent", "sig/node", "2024-01-15T00:00:00Z"),
    ]
    changes = {c.key: c for c in build_timeline_changes(events)}
    first, second = changes["ghe:E1"], changes["ghe:E2"]
    assert (first.seq, second.seq) == (1, 2)
    assert first.valid_to == second.at
    assert second.valid_to == VALID_TO_OPEN
    assert second.previous_key == "ghe:E1"
    assert not second.is_reversal  # add/remove churn is not a reversal
    assert changes["ghe:E3"].seq == 1 and changes["ghe:E3"].previous_key is None


def test_milestone_events_and_valid_from() -> None:
    events = [
        _ms(1, "MilestonedEvent", "v1.34", "2025-05-06T18:25:07Z"),
        _ms(2, "DemilestonedEvent", "v1.34", "2025-07-11T12:38:46Z"),
        _ms(3, "MilestonedEvent", "v1.35", "2025-09-19T16:48:28Z"),
        _lab(4, "LabeledEvent", "tracked/yes", "2025-10-06T05:06:27Z"),
    ]
    changes = build_timeline_changes(events)
    ms = [c for c in changes if c.kind == "milestone"]
    assert [(c.op, c.from_value, c.to_value, c.release) for c in ms] == [
        ("milestoned", None, "v1.34", "v1.34"),
        ("demilestoned", "v1.34", None, None),
        ("milestoned", None, "v1.35", "v1.35"),
    ]
    assert milestone_valid_from(changes, "v1.35") == ms[2].at
    assert label_valid_from(changes, "tracked/yes") == changes[-1].at
    assert label_valid_from(changes, "stage/beta") is None


def test_milestone_move_back_is_reversal() -> None:
    events = [
        _ms(1, "MilestonedEvent", "v1.35", "2025-01-01T00:00:00Z"),
        _ms(2, "MilestonedEvent", "v1.36", "2025-02-01T00:00:00Z"),
        _ms(3, "MilestonedEvent", "v1.35", "2025-03-01T00:00:00Z"),
    ]
    changes = build_timeline_changes(events)
    assert [c.is_reversal for c in changes] == [False, False, True]
