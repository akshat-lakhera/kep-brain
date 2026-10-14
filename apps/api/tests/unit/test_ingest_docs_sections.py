"""README splitting, GitHub anchors, section kinds and reference resolution."""

from __future__ import annotations

from typing import Any

import pytest

from app.ingest.docs import EdgeSpec, Interval, RefResolver, _combine_replacements, _replay
from app.ingest.sections import Slugger, classify, heading_text, headings, slugify, split_sections, summary_text
from app.schema.labels import VALID_TO_OPEN


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Summary", "summary"),
        ("Non-Goals", "non-goals"),
        ("Upgrade / Downgrade Strategy", "upgrade--downgrade-strategy"),
        ("Production Readiness Review Questionnaire", "production-readiness-review-questionnaire"),
        ("Feature Enablement and Rollback", "feature-enablement-and-rollback"),
        ("Story 1: Pod's resources", "story-1-pods-resources"),
        ("API changes (v1.27+)", "api-changes-v127"),
        ("snake_case heading", "snake_case-heading"),
    ],
)
def test_slugify(text: str, slug: str) -> None:
    assert slugify(text) == slug


def test_heading_text_strips_markdown() -> None:
    assert heading_text("[Link](http://x) and `code` **bold**") == "Link and code bold"


def test_slugger_dedup_like_github() -> None:
    s = Slugger()
    assert [s.slug("Notes"), s.slug("Notes"), s.slug("Notes-1"), s.slug("Notes")] == [
        "notes",
        "notes-1",
        "notes-1-1",
        "notes-2",
    ]


@pytest.mark.parametrize(
    ("heading", "kind"),
    [
        ("Summary", "summary"),
        ("Motivation", "motivation"),
        ("Goals", "goals"),
        ("Non-Goals", "non_goals"),
        ("Proposal", "proposal"),
        ("Design Details", "design_details"),
        ("Graduation Criteria", "graduation_criteria"),
        ("Upgrade / Downgrade Strategy", "upgrade_downgrade"),
        ("Version Skew Strategy", "version_skew"),
        ("Production Readiness Review Questionnaire", "prr_questionnaire"),
        ("Implementation History", "implementation_history"),
        ("Drawbacks", "drawbacks"),
        ("Alternatives", "alternatives"),
        ("Release Signoff Checklist", "other"),
    ],
)
def test_classify(heading: str, kind: str) -> None:
    assert classify(heading) == kind


README = """# KEP-1: Title

<!-- toc -->
- [Summary](#summary)
<!-- /toc -->

## Summary

Short summary. Contact a@example.com.

## Motivation

### Goals

- one

```yaml
## not a heading
```

## Notes

## Notes

## Implementation History

- 2020-01-01: created
"""


def test_split_sections() -> None:
    secs = split_sections(README)
    assert [s.anchor for s in secs] == ["summary", "motivation", "notes", "notes-1", "implementation-history"]
    assert [s.kind for s in secs] == ["summary", "motivation", "other", "other", "implementation_history"]
    assert [s.order for s in secs] == [0, 1, 2, 3, 4]
    assert "## not a heading" in secs[1].text
    assert "a@example.com" not in secs[0].text
    assert summary_text(secs) == "Short summary. Contact [email removed]."


def test_headings_ignore_fenced_code() -> None:
    assert [h.text for h in headings(README)] == [
        "KEP-1: Title",
        "Summary",
        "Motivation",
        "Goals",
        "Notes",
        "Notes",
        "Implementation History",
    ]


def test_large_block_splits_at_level_three() -> None:
    body = "x" * 7000
    md = (
        f"## Design Details\n\nintro\n\n### Test Plan\n\n{body}\n\n"
        "### Graduation Criteria\n\nGA\n\n## Drawbacks\n\nnone\n"
    )
    secs = split_sections(md)
    assert [(s.heading, s.level) for s in secs] == [
        ("Design Details", 2),
        ("Test Plan", 3),
        ("Graduation Criteria", 3),
        ("Drawbacks", 2),
    ]
    assert secs[0].text == "intro"
    assert secs[2].kind == "graduation_criteria"


def _resolver() -> RefResolver:
    dirs = [
        "keps/sig-scheduling/583-coscheduling",
        "keps/sig-scheduling/4671-gang-scheduling",
        "keps/sig-scheduling/5027-dra-admin-controlled-device-attributes",
        "keps/sig-node/2133-kubelet-credential-providers",
        "keps/sig-cloud-provider/2133-out-of-tree-credential-provider",
    ]
    numbers = {583: [dirs[0]], 4671: [dirs[1]], 5027: [dirs[2]], 2133: [dirs[3], dirs[4]]}
    renames = {
        "keps/sig-cloud-provider/20191004-out-of-tree-credential-providers.md": (
            "keps/sig-cloud-provider/2133-out-of-tree-credential-provider/README.md"
        )
    }
    return RefResolver(dirs, numbers, renames)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/keps/sig-scheduling/583-coscheduling", ("kep", "keps/sig-scheduling/583-coscheduling")),
        ("keps/sig-scheduling/583-coscheduling/", ("kep", "keps/sig-scheduling/583-coscheduling")),
        ("/keps/sig-scheduling/583-coscheduling/README.md", ("kep", "keps/sig-scheduling/583-coscheduling")),
        ("583-coscheduling", ("kep", "keps/sig-scheduling/583-coscheduling")),
        ("4671-renamed-slug", ("kep", "keps/sig-scheduling/4671-gang-scheduling")),
        ("583", ("kep", "keps/sig-scheduling/583-coscheduling")),
        ("KEP-4671", ("kep", "keps/sig-scheduling/4671-gang-scheduling")),
        (
            "/keps/sig-cloud-provider/20191004-out-of-tree-credential-providers.md",
            ("kep", "keps/sig-cloud-provider/2133-out-of-tree-credential-provider"),
        ),
        (
            "/keps/sig-node/5027-dra-admin-controlled-device-attributes",
            ("kep", "keps/sig-scheduling/5027-dra-admin-controlled-device-attributes"),
        ),
        ("/keps/sig-scheduling/4671", ("kep", "keps/sig-scheduling/4671-gang-scheduling")),
        (
            "https://github.com/kubernetes/enhancements/tree/master/keps/sig-scheduling/583-coscheduling",
            ("kep", "keps/sig-scheduling/583-coscheduling"),
        ),
        ("https://docs.google.com/document/d/abc/edit", ("external", "https://docs.google.com/document/d/abc/edit")),
        ("/keps/sig-ccc/3456-replaced-kep", None),
        ("N/A", None),
        ("n/a", None),
        ("none", None),
    ],
)
def test_reference_resolution(raw: str, expected: tuple[str, str] | None) -> None:
    assert _resolver().resolve(raw, "keps/sig-scheduling/5832-decouple-podgroup-api") == expected


def test_number_ambiguity_prefers_same_sig() -> None:
    assert _resolver().resolve("2133", "keps/sig-node/9999-x") == (
        "kep",
        "keps/sig-node/2133-kubelet-credential-providers",
    )


def test_replay_intervals_close_and_reopen() -> None:
    spec: EdgeSpec = ("APPROVES", "Person", "alice", "KEP", "k", ())
    steps: list[tuple[int, str, dict[EdgeSpec, dict[str, Any]]]] = [
        (100, "u1", {spec: {}}),
        (200, "u2", {}),
        (300, "u3", {spec: {}}),
        (250, "u4", {spec: {}}),
    ]
    ivs = sorted(_replay(steps, "head"), key=lambda i: i.valid_from)
    assert [(i.valid_from, i.valid_to, i.source_url) for i in ivs] == [(100, 200, "u1"), (300, VALID_TO_OPEN, "head")]


def test_one_sided_replacement_is_derived() -> None:
    succ = Interval(
        ("DECL", "successor", "keps/a/2-new", "KEP", "keps/a/1-old", ()), {"raw": "1"}, 100, VALID_TO_OPEN, "s"
    )
    out = _combine_replacements([succ])
    rep = next(i for i in out if i.spec[0] == "REPLACES")
    sup = next(i for i in out if i.spec[0] == "SUPERSEDED_BY")
    assert rep.spec[2:5] == ("keps/a/2-new", "KEP", "keps/a/1-old")
    assert rep.props["declared_by"] == "successor"
    assert sup.spec[2:5] == ("keps/a/1-old", "KEP", "keps/a/2-new")
    assert sup.props["derived"] is True


def test_both_sides_declared_after_predecessor_catches_up() -> None:
    succ = Interval(("DECL", "successor", "n", "KEP", "o", ()), {"raw": "o"}, 100, VALID_TO_OPEN, "s")
    pred = Interval(("DECL", "predecessor", "n", "KEP", "o", ()), {"raw": "n"}, 200, VALID_TO_OPEN, "p")
    reps = sorted(
        (i for i in _combine_replacements([succ, pred]) if i.spec[0] == "REPLACES"), key=lambda i: i.valid_from
    )
    assert [(i.valid_from, i.valid_to, i.props["declared_by"]) for i in reps] == [
        (100, 200, "successor"),
        (200, VALID_TO_OPEN, "both"),
    ]
    sups = [
        i for i in _combine_replacements([succ, pred]) if i.spec[0] == "SUPERSEDED_BY" and i.valid_to == VALID_TO_OPEN
    ]
    assert sups[0].props["derived"] is False
