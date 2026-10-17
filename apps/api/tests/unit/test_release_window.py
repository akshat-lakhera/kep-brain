"""The shared "since release X" window and the lean contradiction rows."""

from __future__ import annotations

from typing import Any

import pytest

from app.tools.releases import ISSUE_START, KEP_YAML_START, RELEASE_FALLBACK, window_start
from app.tools.t03.audit import lean_hit


def _query(answers: dict[str, Any], release: dict[str, Any] | None = None):
    calls: list[str] = []

    async def query(statement: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        calls.append(statement)
        assert args["release"] == "v1.38"
        if statement == RELEASE_FALLBACK:
            return [release] if release is not None else []
        return [{"t": answers.get(statement)}]

    return query, calls


@pytest.mark.asyncio
async def test_window_opens_with_the_first_issue_milestone_event() -> None:
    query, calls = _query({ISSUE_START: 1_700_000_000, KEP_YAML_START: 1_600_000_000})
    assert await window_start(query, "v1.38") == (1_700_000_000, "tracking_issue_milestone")
    assert calls == [ISSUE_START]


@pytest.mark.asyncio
async def test_window_falls_back_to_kep_yaml_then_release_facts() -> None:
    query, _ = _query({KEP_YAML_START: 1_600_000_000})
    assert await window_start(query, "v1.38") == (1_600_000_000, "kep_yaml_milestone")
    # A planned release nobody has milestoned yet: from when it appeared in the graph.
    query, _ = _query({}, {"first_seen": 1_500_000_000.0, "released": None, "is_future": True})
    assert await window_start(query, "v1.38") == (1_500_000_000, "release_first_seen")
    # A shipped release with no milestone events on record: from its ship date.
    query, _ = _query({}, {"first_seen": 1_700_000_000, "released": 1_400_000_000, "is_future": False})
    assert await window_start(query, "v1.38") == (1_400_000_000, "release_date")
    # Older than every record (v1.1 and friends): everything, never "nothing since the sync".
    query, _ = _query({}, {"first_seen": 1_700_000_000, "released": None, "is_future": False})
    assert await window_start(query, "v1.38") == (0, "all_history")
    query, _ = _query({})
    assert await window_start(query, "v1.38") is None


def test_lean_hit_keeps_both_sides_and_citable_records() -> None:
    hit = {
        "finding": {
            "label": "Finding",
            "key": "fnd:x",
            "title": "t",
            "url": "u",
            "kind": "stage_mismatch",
            "kep_path": "k",
            "state": "open",
            "a_label": "kep.yaml stage",
            "a_value": "beta",
            "a_url": "ua",
            "b_label": "issue label",
            "b_value": "stage/alpha",
            "b_url": "ub",
            "suggested_fix": "set_stage_alpha",
            "detected_at_iso": "d",
        },  # fmt: skip
        "kep": {
            "label": "KEP",
            "key": "k",
            "title": "K",
            "url": "uk",
            "evidence_id": "e1",
            "number": 7,
            "owning_sig": "sig-node",
            "status": "implementable",
            "stage": "beta",
            "summary": "long",
        },  # fmt: skip
        "tracking_issue": [
            {"label": "Issue", "key": "i", "evidence_id": "e2", "state": "closed", "labels_current": []},
        ],
        "evidence": [{"node": {"key": "doc"}, "evidence_kind": "kep_yaml"}],
    }
    lean = lean_hit(hit, keep_evidence=False)
    assert lean["finding"] == {
        "kind": "stage_mismatch", "state": "open", "a_label": "kep.yaml stage", "a_value": "beta",
        "b_label": "issue label", "b_value": "stage/alpha", "suggested_fix": "set_stage_alpha",
    }  # fmt: skip
    assert lean["kep"]["evidence_id"] == "e1" and "summary" not in lean["kep"]
    assert lean["tracking_issue"][0] == {"label": "Issue", "key": "i", "evidence_id": "e2", "state": "closed"}
    assert "evidence" not in lean
    assert lean_hit(hit, keep_evidence=True)["evidence"] == hit["evidence"]
    assert lean_hit({"kep": {}, "contradictions": 0}, keep_evidence=True) == {"kep": {}, "contradictions": 0}
