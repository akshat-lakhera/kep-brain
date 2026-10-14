"""Claim validator (02 §6.3): deterministic acceptance and rejection rules."""

from __future__ import annotations

from app.agent.validator import Claim, FinalAnswer, collect_row_urls, normalise_markers, validate
from app.db.results import Evidence, evidence_id

KEP_URL = "https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/583-coscheduling"
ISSUE_URL = "https://github.com/kubernetes/enhancements/issues/583"


def ev(label: str, key: str, url: str) -> Evidence:
    return Evidence(evidence_id=evidence_id(label, key), label=label, key=key, title=key, url=url)


KEP = ev("KEP", "keps/sig-scheduling/583-coscheduling", KEP_URL)
ISSUE = ev("Issue", "kubernetes/enhancements#583", ISSUE_URL)
FINDING = ev("Finding", "fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling", ISSUE_URL)
EVIDENCE = {e.evidence_id: e for e in (KEP, ISSUE, FINDING)}


def answer(md: str, claims: list[list[str]], abstained: bool = False) -> FinalAnswer:
    return FinalAnswer(
        answer_markdown=md,
        claims=[Claim(text="c", evidence_ids=ids) for ids in claims],
        abstained=abstained,
    )


def test_valid_answer_is_numbered() -> None:
    a = answer(f"Status is provisional [[{KEP.evidence_id}]]; the issue is closed [[{ISSUE.evidence_id}]].",
               [[KEP.evidence_id], [ISSUE.evidence_id]])  # fmt: skip
    v = validate(a, EVIDENCE, set())
    assert not v.abstained
    assert v.answer_markdown == "Status is provisional [1]; the issue is closed [2]."
    assert [c.key for c in v.citations] == [KEP.key, ISSUE.key]


def test_unknown_inline_id_abstains() -> None:
    a = answer("Made up [[aaaaaaaaaaaa]].", [[KEP.evidence_id]])
    v = validate(a, EVIDENCE, set())
    assert v.abstained and v.abstain_reason == "unsupported_claims" and v.answer_markdown == ""


def test_claim_with_unseen_id_abstains() -> None:
    a = answer(f"Fine [[{KEP.evidence_id}]].", [["bbbbbbbbbbbb"]])
    assert validate(a, EVIDENCE, set()).abstained


def test_finding_is_not_citable() -> None:
    a = answer(f"Contradiction [[{FINDING.evidence_id}]].", [[FINDING.evidence_id]])
    v = validate(a, EVIDENCE, set())
    assert v.abstained and v.abstain_reason == "unsupported_claims"


def test_answer_without_claims_or_citations_abstains() -> None:
    assert validate(answer("No citations here.", []), EVIDENCE, set()).abstained
    assert validate(answer("No inline marker.", [[KEP.evidence_id]]), EVIDENCE, set()).abstained


def test_urls_not_from_rows_are_removed() -> None:
    md = f"See [the issue]({ISSUE_URL}) and [elsewhere](https://evil.example/x) https://evil.example/y "
    md += f"[[{KEP.evidence_id}]]"
    v = validate(answer(md, [[KEP.evidence_id]]), EVIDENCE, set())
    assert not v.abstained
    assert ISSUE_URL in v.answer_markdown
    assert "evil.example" not in v.answer_markdown and "elsewhere" in v.answer_markdown


def test_row_urls_are_allowed() -> None:
    rows = [{"finding": {"a_url": "https://github.com/kubernetes/enhancements/blob/x/kep.yaml"}}]
    urls: set[str] = set()
    collect_row_urls(rows, urls)
    md = f"File https://github.com/kubernetes/enhancements/blob/x/kep.yaml [[{KEP.evidence_id}]]"
    v = validate(answer(md, [[KEP.evidence_id]]), EVIDENCE, urls)
    assert "blob/x/kep.yaml" in v.answer_markdown


def test_abstention_may_name_nearest_records() -> None:
    a = answer(f"No exact match; nearest is KEP-583 [[{KEP.evidence_id}]].", [[KEP.evidence_id]], abstained=True)
    v = validate(a, EVIDENCE, set())
    assert v.abstained and v.abstain_reason == "no_evidence"
    assert v.answer_markdown.endswith("[1].") and v.citations[0].key == KEP.key


def test_abstention_with_bad_id_shows_nothing() -> None:
    a = answer("Nearest [[cccccccccccc]].", [], abstained=True)
    v = validate(a, EVIDENCE, set())
    assert v.abstained and v.answer_markdown == ""


def test_marker_variants_are_normalised() -> None:
    a, b = KEP.evidence_id, ISSUE.evidence_id
    assert normalise_markers(f"x [[{a}, {b}]]") == f"x [[{a}]][[{b}]]"
    assert normalise_markers(f"x [[{a}], [{b}]]") == f"x [[{a}]][[{b}]]"
    v = validate(answer(f"x [[{a}], [{b}]].", [[a, b]]), EVIDENCE, set())
    assert v.answer_markdown == "x [1][2]."


def test_plain_words_in_brackets_are_not_citations() -> None:
    v = validate(answer(f"KEP (coscheduling) [[{KEP.evidence_id}]]", [[KEP.evidence_id]]), EVIDENCE, set())
    assert not v.abstained and "(coscheduling)" in v.answer_markdown
