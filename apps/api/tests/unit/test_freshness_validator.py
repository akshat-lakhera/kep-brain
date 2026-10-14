"""The deterministic validator for the freshness agent's answer, and the spend estimate."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.worker.freshness import EvidenceRow, TriageRejected, estimate_usd, validate_triage

ISSUE = EvidenceRow(
    "aaaaaaaaaaaa", "Issue", "kubernetes/enhancements#583", "https://github.com/kubernetes/enhancements/issues/583", {}
)
KEP = EvidenceRow(
    "bbbbbbbbbbbb", "KEP", "keps/sig-scheduling/583-x", "https://github.com/kubernetes/enhancements/tree/x", {}
)
ROWS = [ISSUE, KEP]


def answer(**over: Any) -> str:
    base: dict[str, Any] = {
        "triage_verdict": "confirmed",
        "assessment": "Issue is closed [aaaaaaaaaaaa] while kep.yaml says provisional [bbbbbbbbbbbb].",
        "suggested_fix": "set_status_implemented",
        "confidence": 0.9,
    }
    return json.dumps(base | over)


def test_valid_answer_is_accepted() -> None:
    t = validate_triage(answer(), ROWS)
    assert (t.verdict, t.suggested_fix, t.confidence) == ("confirmed", "set_status_implemented", 0.9)
    assert t.evidence_ids == ["aaaaaaaaaaaa", "bbbbbbbbbbbb"]


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        answer(triage_verdict="maybe"),
        answer(suggested_fix="rewrite_everything"),
        answer(confidence=1.5),
        answer(confidence=True),
        answer(confidence="high"),
        answer(assessment=""),
        answer(assessment="x [aaaaaaaaaaaa] " + "y" * 600),
        answer(assessment="No citation at all."),
        answer(assessment="Cites a stranger [cccccccccccc]."),
        answer(assessment="Cites one real [aaaaaaaaaaaa] and one made up [cccccccccccc]."),
        answer(assessment="See https://example.com/fake [aaaaaaaaaaaa]."),
    ],
)
def test_invalid_answers_are_rejected(raw: str) -> None:
    with pytest.raises(TriageRejected):
        validate_triage(raw, ROWS)


def test_a_given_url_may_be_quoted() -> None:
    raw = answer(assessment=f"Closed, see {ISSUE.url}. [aaaaaaaaaaaa]")
    assert validate_triage(raw, ROWS).evidence_ids == ["aaaaaaaaaaaa"]


def test_cost_estimate_uses_model_price_and_falls_back() -> None:
    assert estimate_usd("openai/gpt-oss-20b", 1_000_000, 1_000_000) == pytest.approx(0.60)
    assert estimate_usd("some-new-model", 1_000_000, 0) == pytest.approx(0.59)
