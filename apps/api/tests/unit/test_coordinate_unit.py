"""Draft composition and the verifier's check, on in-memory evidence (no database)."""

from __future__ import annotations

from app.worker.coordinate import check_draft, compose_draft
from app.worker.freshness import EvidenceRow, FindingContext

A_URL = "https://github.com/kubernetes/enhancements/blob/pin/keps/sig-scheduling/583-x/kep.yaml"
B_URL = "https://github.com/kubernetes/enhancements/issues/583"
ROWS = [
    EvidenceRow(
        "bbbbbbbbbbbb",
        "KEP",
        "keps/sig-scheduling/583-x",
        "https://github.com/kubernetes/enhancements/tree/pin/x",
        {"number": 583},
    ),
    EvidenceRow("aaaaaaaaaaaa", "Issue", "kubernetes/enhancements#583", B_URL, {}),
]


def context(assessment: str | None = "Issue closed [aaaaaaaaaaaa].") -> FindingContext:
    sides = {"a_label": "kep.yaml status", "a_value": "provisional", "a_url": A_URL,
             "b_label": "issue #583 state", "b_value": "closed (completed)", "b_url": B_URL}  # fmt: skip
    return FindingContext("fnd:x", "active_status_closed_issue", "triaged", sides, "set_status_implemented", ROWS,
                          "confirmed", assessment, 0.9)  # fmt: skip


def test_draft_cites_both_sides_and_passes_the_check() -> None:
    ctx = context()
    title, body = compose_draft(ctx)
    assert "KEP-583" in title
    assert A_URL in body and B_URL in body
    assert "[1](" + B_URL + ")" in body and "aaaaaaaaaaaa" not in body
    assert check_draft(ctx, title, body, [f"{r.label}|{r.key}" for r in ROWS]) == []


def test_check_rejects_foreign_urls_missing_sides_and_unknown_keys() -> None:
    ctx = context()
    title, body = compose_draft(ctx)
    problems = check_draft(ctx, title, body + "\nhttps://example.com/other", ["Issue|kubernetes/enhancements#999"])
    assert any("example.com" in p for p in problems)
    assert any("kubernetes/enhancements#999" in p for p in problems)
    assert any("missing source link" in p for p in check_draft(ctx, title, body.replace(A_URL, "(removed)"), []))
    assert "empty title" in check_draft(ctx, " ", body, [])
