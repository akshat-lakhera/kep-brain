from __future__ import annotations

from typing import Any

import pytest

from app.eval.questions import judge_questions, load_questions, public_question
from app.eval.runner import render_report, select_questions
from app.eval.scoring import first_tool_hit, percentile, score_row, summarise, wilson

STA04 = {
    "id": "STA-04",
    "kind": "STA",
    "expected_evidence": [
        {"label": "KEP", "key": "keps/sig-scheduling/583-coscheduling"},
        {"label": "Issue", "key": "kubernetes/enhancements#583"},
    ],
    "expected_evidence_any": [
        {"label": "KEP", "key": "keps/sig-scheduling/4671-gang-scheduling"},
        {"label": "KEP", "key": "keps/sig-scheduling/5832-decouple-podgroup-api"},
    ],
    "expected_tools": {"first": "find_contradictions", "set": ["find_contradictions", "get_kep"]},
}
ABS10 = {"id": "ABS-10", "kind": "ABS", "accept": ["no_evidence"], "accept_explicit_negative": False}
ABS09 = {
    "id": "ABS-09",
    "kind": "ABS",
    "accept": ["no_evidence"],
    "accept_explicit_negative": True,
    "explicit_negative_evidence": [{"label": "KEP", "key": "keps/sig-apps/3541-x"}],
}
CHT = {
    "id": "CHT-03",
    "kind": "CHT",
    "expected_evidence": [{"label": "PullRequest", "key": "kubernetes/enhancements#4904"}],
    "require_any_label": ["Review", "Comment"],
}
UNKNOWN = {"id": "OWN-04", "kind": "OWN", "expected_evidence": "unknown"}


def cite(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"label": label, "key": key, "url": "https://example.test"} for label, key in pairs]


def row(citations: list[dict[str, str]], abstained: bool = False, reason: str | None = None, **extra: Any) -> dict:
    return {"abstained": abstained, "abstain_reason": reason, "citations": citations, **extra}


FULL = cite(
    ("KEP", "keps/sig-scheduling/583-coscheduling"),
    ("Issue", "kubernetes/enhancements#583"),
    ("KEP", "keps/sig-scheduling/5832-decouple-podgroup-api"),
)


def test_answer_citing_all_expected_keys_passes() -> None:
    out = score_row(STA04, row(FULL))
    assert out["passed"] is True
    assert out["recall"] == 1.0


def test_missing_expected_key_fails_with_partial_recall() -> None:
    out = score_row(STA04, row(FULL[:1] + FULL[2:]))
    assert out["passed"] is False
    assert out["recall"] == 0.5


def test_any_of_group_needs_one_successor() -> None:
    out = score_row(STA04, row(FULL[:2]))
    assert out["passed"] is False
    assert out["recall"] == 1.0


def test_section_citation_counts_for_its_kep() -> None:
    sections = cite(
        ("Section", "keps/sig-scheduling/583-coscheduling#summary"),
        ("Issue", "kubernetes/enhancements#583"),
        ("KEP", "keps/sig-scheduling/4671-gang-scheduling"),
    )
    assert score_row(STA04, row(sections))["passed"] is True


def test_key_prefix_is_not_a_match() -> None:
    other = cite(("Issue", "kubernetes/enhancements#5830"), ("KEP", "keps/sig-scheduling/583-coscheduling-v2"))
    assert score_row(STA04, row(other))["passed"] is False


def test_abstaining_on_answerable_question_is_false_abstention() -> None:
    out = score_row(STA04, row([], abstained=True, reason="no_evidence"))
    assert out["passed"] is False
    assert out["false_abstention"] is True


def test_unknown_expected_evidence_is_unscored() -> None:
    assert score_row(UNKNOWN, row(FULL))["passed"] is None
    assert score_row(UNKNOWN, row([], abstained=True, reason="no_evidence"))["passed"] is False


def test_thread_question_needs_review_or_comment_label() -> None:
    pr_only = cite(("PullRequest", "kubernetes/enhancements#4904"))
    assert score_row(CHT, row(pr_only))["passed"] is False
    with_comment = pr_only + cite(("Comment", "kubernetes/enhancements/issues/comments/1"))
    assert score_row(CHT, row(with_comment))["passed"] is True


def test_abstention_question_requires_accepted_reason() -> None:
    assert score_row(ABS10, row([], abstained=True, reason="no_evidence"))["passed"] is True
    assert score_row(ABS10, row([], abstained=True, reason="out_of_scope"))["passed"] is False
    assert score_row(ABS10, row(FULL))["passed"] is False


def test_validator_rescue_counts_as_weaker_success() -> None:
    out = score_row(ABS10, row([], abstained=True, reason="unsupported_claims"))
    assert out["passed"] is True
    assert out["rescue"] is True


def test_explicit_negative_needs_the_named_file_cited() -> None:
    named = cite(("KEP", "keps/sig-apps/3541-x"))
    assert score_row(ABS09, row(named))["passed"] is True
    assert score_row(ABS09, row(cite(("KEP", "keps/sig-apps/other"))))["passed"] is False
    assert score_row(ABS10, row(named))["passed"] is False


def test_first_tool_hit() -> None:
    assert first_tool_hit(STA04, {"tools": ["find_contradictions", "get_kep"]}) is True
    assert first_tool_hit(STA04, {"tools": ["get_kep"]}) is False
    assert first_tool_hit(STA04, {"tools": []}) is None
    assert first_tool_hit(UNKNOWN, {"tools": ["get_kep"]}) is None


def test_wilson_interval_and_percentile() -> None:
    assert wilson(0, 0) is None
    low, high = wilson(8, 10) or (0, 0)
    assert 0.49 < low < 0.50 and 0.94 < high < 0.95
    assert percentile([], 50) is None
    assert percentile([5, 1, 3, 2, 4], 50) == 3
    assert percentile([5, 1, 3, 2, 4], 95) == 5


def test_summary_groups_by_arm_and_kind() -> None:
    questions = {q["id"]: q for q in (STA04, ABS10, UNKNOWN)}
    rows = [
        {
            "arm": "G",
            "qid": "STA-04",
            "rep": 1,
            "latency_ms": 100,
            "tools_ms": 10.0,
            "cost_usd": 0.01,
            "tools": ["find_contradictions"],
            **row(FULL),
        },
        {"arm": "G", "qid": "ABS-10", "rep": 1, "latency_ms": 300, "cost_usd": 0.02, **row([], True, "no_evidence")},
        {"arm": "G", "qid": "OWN-04", "rep": 1, "latency_ms": 200, "cost_usd": 0.0, **row(FULL)},
        {"arm": "N", "qid": "STA-04", "rep": 1, "cost_usd": 0.001, **row([], True, "unsupported_claims")},
    ]
    summary = summarise(questions, rows)
    g = summary["overall"]["G"]
    assert (g["n"], g["scored"], g["unscored"], g["passed"], g["accuracy"]) == (3, 2, 1, 2, 1.0)
    assert g["first_tool_hit_rate"] == 1.0
    assert g["cost_usd"] == 0.03
    n = summary["overall"]["N"]
    assert (n["passed"], n["false_abstentions"], n["false_abstention_rate"]) == (0, 1, 1.0)
    assert set(summary["by_kind"]) == {"G/STA", "G/ABS", "G/OWN", "N/STA"}
    assert len(summary["per_question"]) == 4


def test_summary_is_deterministic() -> None:
    questions = {STA04["id"]: STA04}
    rows = [{"arm": "G", "qid": "STA-04", "rep": 1, **row(FULL)}]
    assert summarise(questions, rows) == summarise(questions, rows)


def test_report_renders_markdown_table() -> None:
    questions = {STA04["id"]: STA04}
    agg = summarise(questions, [{"arm": "G", "qid": "STA-04", "rep": 1, **row(FULL)}])
    text = render_report({"run_id": "r1", "rows": 1, "errors": 0, "cost_usd": 0.0, "complete": True, **agg})
    assert "| G | STA | 1 | 1 | 1 | 100% | 0 | 0 |" in text


def test_question_file_matches_design_counts() -> None:
    questions = load_questions()
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids)) == 64
    kinds = {k: sum(1 for q in questions if q["kind"] == k) for k in {q["kind"] for q in questions}}
    assert kinds == {"OWN": 10, "EXP": 7, "DEC": 8, "STA": 10, "MH": 14, "CHT": 4, "ABS": 11}
    judged = judge_questions(questions)
    assert [q["id"] for q in judged] == ["STA-04", "DEC-07", "DEC-01", "MH-07", "ABS-10"]
    assert public_question(judged[0])["text"].startswith("What is the status of KEP-583")
    assert all(q["accept"] for q in questions if q["kind"] == "ABS")


def test_question_selection() -> None:
    questions = load_questions()
    assert [q["id"] for q in select_questions(questions, "judge")][0] == "STA-04"
    first = [q["id"] for q in select_questions(questions, "all")]
    assert first == [q["id"] for q in select_questions(questions, "all")]
    assert sorted(first) == sorted(q["id"] for q in questions)


@pytest.mark.parametrize("qid", ["STA-04", "DEC-07", "DEC-01", "MH-07", "ABS-10"])
def test_judge_questions_carry_expectations(qid: str) -> None:
    q = next(q for q in load_questions() if q["id"] == qid)
    assert q["expected_evidence"] != "unknown" or q["kind"] == "ABS"
