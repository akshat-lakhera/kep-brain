"""Finding helpers and lifecycle transitions (03 §4.7, §7.5)."""

from __future__ import annotations

from app.ingest.findings import (
    Hit,
    closed_reason_text,
    future_targets,
    milestone_fix,
    plan_lifecycle,
    stage_conflicts,
    stage_fix,
    suggested_fix_for_closed,
)

NOW = 1_800_000_000


def _hit(kep: str = "keps/sig-scheduling/583-coscheduling", successor: str | None = None) -> Hit:
    return Hit(
        kind="one_sided_replacement" if successor else "active_status_closed_issue",
        kep_key=kep,
        successor_key=successor,
        a_label="kep.yaml status",
        a_value="provisional",
        a_url="https://github.com/a",
        b_label="issue #583 state",
        b_value="closed (completed) on 2019-09-09",
        b_url="https://github.com/b",
        suggested_fix="set_status_implemented",
    )


def test_keys() -> None:
    assert _hit().key == "fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling"
    assert (
        _hit(successor="keps/sig-scheduling/4671-gang-scheduling").key
        == "fnd:one_sided_replacement:keps/sig-scheduling/583-coscheduling:keps/sig-scheduling/4671-gang-scheduling"
    )


def test_new_hit_is_open() -> None:
    updates, resolved, counts = plan_lifecycle([_hit()], {}, NOW)
    assert resolved == [] and counts["created"] == 1
    props = updates[0].props
    assert props["state"] == "open" and props["reopened_count"] == 0 and props["detected_at"] == NOW
    assert props["source_url"] == props["a_url"]


def test_existing_hit_keeps_state_and_triage() -> None:
    updates, _, counts = plan_lifecycle([_hit()], {_hit().key: ("triaged", 0)}, NOW)
    props = updates[0].props
    assert "state" not in props and "detected_at" not in props
    assert not any(k.startswith("triage") or k == "assessment" for k in props)
    assert counts["confirmed"] == 1 and props["last_confirmed_at"] == NOW


def test_recurrence_reopens() -> None:
    updates, _, counts = plan_lifecycle([_hit()], {_hit().key: ("resolved_upstream", 2)}, NOW)
    assert updates[0].props["state"] == "open" and updates[0].props["reopened_count"] == 3
    assert counts["reopened"] == 1


def test_gone_findings_resolve_except_dismissed() -> None:
    existing = {
        "fnd:a": ("open", 0),
        "fnd:b": ("dismissed", 0),
        "fnd:c": ("resolved_upstream", 0),
        "fnd:d": ("drafted", 0),
    }
    _, resolved, counts = plan_lifecycle([], existing, NOW)
    assert resolved == ["fnd:a", "fnd:d"] and counts["resolved"] == 2


def test_suggested_fix_by_state_reason() -> None:
    assert suggested_fix_for_closed("completed") == "set_status_implemented"
    assert suggested_fix_for_closed("completed", "2023-01-12") == "set_status_implemented"
    assert suggested_fix_for_closed("not_planned") == "set_status_withdrawn_or_deferred"
    assert suggested_fix_for_closed(None) == "other"


def test_bot_and_pre_reason_closures_only_ask_for_a_review() -> None:
    # GitHub backfilled every closure before 2022-05-19 as "completed": the reason carries no information.
    assert suggested_fix_for_closed("completed", "2019-09-09") == "review_status"
    assert suggested_fix_for_closed("completed", "2022-05-18") == "review_status"
    assert suggested_fix_for_closed("completed", "2022-05-19") == "set_status_implemented"
    # The lifecycle bot closes inactive issues; that is not a decision about the KEP.
    assert suggested_fix_for_closed("completed", "2024-01-01", ["lifecycle/rotten", "stage/beta"]) == "review_status"
    assert suggested_fix_for_closed("not_planned", "2024-01-01", ["lifecycle/stale"]) == "review_status"
    assert closed_reason_text("completed", "2019-09-09") == "reason not recorded"
    assert closed_reason_text("completed", "2023-01-12") == "completed"
    assert closed_reason_text(None, "2023-01-12") == "no reason"


def test_milestone_fix_by_issue_state_and_release_window() -> None:
    # Latest shipped release v1.37: v1.38 is in development, v1.39 is next; both are normal in-flight drift.
    assert milestone_fix("open", "v1.38", 37) == "in_flight_wait_for_freeze"
    assert milestone_fix("open", "v1.39", 37) == "in_flight_wait_for_freeze"
    assert milestone_fix("open", "v1.40", 37) == "update_latest_milestone"
    assert milestone_fix("open", "v1.36", 37) == "update_latest_milestone"
    assert milestone_fix("open", "v1.38", None) == "update_latest_milestone"  # no shipped release known
    assert milestone_fix("closed", "v1.25", 37) == "none_historical_label"


def test_stage_fix_prefers_the_newer_record() -> None:
    assert stage_fix(1_700_000_000, 1_600_000_000) == "none_historical_label"  # kep.yaml changed after the close
    assert stage_fix(1_600_000_000, 1_700_000_000) == "update_stage"
    assert stage_fix(None, 1_700_000_000) == "update_stage"
    assert stage_fix(1_700_000_000, None) == "update_stage"


def test_stage_conflicts() -> None:
    assert stage_conflicts("stable", ["stage/beta"])  # KEP-1923
    assert not stage_conflicts("stable", ["stage/stable", "stage/beta"])
    assert not stage_conflicts("stable", [])  # no stage label: not a contradiction


def test_future_targets_kep_5978() -> None:
    targets = {"alpha": ("v1.37", 37, False), "beta": ("v1.38", 38, True), "stable": ("v1.40", 40, True)}
    assert future_targets("v1.37", 37, targets, set()) == {"beta": "v1.38", "stable": "v1.40"}
    # property fallback without Release ordinals: beyond latest-milestone counts
    assert future_targets("v1.30", None, {"beta": ("v1.31", None, None)}, set()) == {"beta": "v1.31"}
    assert future_targets("v1.31", None, {"beta": ("v1.31", None, None)}, set()) == {}
