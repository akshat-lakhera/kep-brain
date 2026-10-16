"""why_designed section parsing, knowledge_risk window, automation-label noise filter, registry surfaces."""

from __future__ import annotations

from app.tools.noise import automation_label_predicate
from app.tools.registry import llm_tools, mcp_tools
from app.tools.t03.rationale import EXCERPT_CHARS, excerpt, part_of, pick_parts, section_blocks
from app.tools.t03.risk import idle_window

URL = "https://github.com/kubernetes/enhancements/blob/sha/keps/sig-x/1-a/README.md"


def sec(order: int, heading: str, anchor: str, text: str, level: int = 2) -> dict[str, object]:
    return {"key": f"keps/sig-x/1-a#{anchor}", "heading": heading, "anchor": anchor, "level": level,
            "order": order, "text": text, "url": f"{URL}#{anchor}"}  # fmt: skip


MOTIVATION = "Why we need it. " * 20 + "\n\n### Goals\n\n- make it fast\n\n### Non-Goals\n\n- make it slow\n"
SECTIONS = [
    sec(0, "Summary", "summary", "Short summary of the change, long enough. " * 10),
    sec(1, "Motivation", "motivation", MOTIVATION),
    sec(2, "Proposal", "proposal", ""),
    sec(3, "Goals", "goals-1", "Another goals heading later in the file", level=3),
    sec(4, "API Changes", "api-changes", "x" * 3000, level=3),
    sec(5, "Risks and Mitigations", "risks-and-mitigations", "Risk text", level=3),
    sec(6, "Drawbacks", "drawbacks", "It costs memory."),
]


def test_embedded_headings_get_document_wide_anchors() -> None:
    blocks = section_blocks(SECTIONS)
    goals = [b for b in blocks if b.heading == "Goals"]
    assert [b.anchor for b in goals] == ["goals", "goals-1"]
    assert goals[0].url == f"{URL}#goals" and goals[0].full == "- make it fast"
    non_goals = next(b for b in blocks if b.heading == "Non-Goals")
    assert non_goals.anchor == "non-goals" and non_goals.full == "- make it slow"


def test_pick_parts_and_proposal_fallback() -> None:
    parts = pick_parts(section_blocks(SECTIONS))
    assert set(parts) == {"summary", "motivation", "goals", "non_goals", "proposal", "risks", "drawbacks"}
    assert parts["proposal"].heading == "API Changes"  # empty split `## Proposal` -> first plain sub-section
    assert parts["goals"].anchor == "goals"  # the one under Motivation comes first in the document
    text, chars = excerpt(parts["proposal"])
    assert len(text) == EXCERPT_CHARS and chars == 3000
    text, chars = excerpt(parts["motivation"])
    assert text.startswith("Why we need it.") and "### Goals" not in text


def test_part_of() -> None:
    assert part_of("Risks and Mitigations") == "risks"
    assert part_of("Alternatives Considered") == "alternatives"
    assert part_of("Non-Goals") == "non_goals"
    assert part_of("Test Plan") is None


def test_idle_window_uses_release_before_last_two() -> None:
    shipped = [
        {"release": "v1.37", "released_at": 300},
        {"release": "v1.36", "released_at": 200},
        {"release": "v1.35", "released_at": 100},
    ]
    t, basis = idle_window(shipped) or (0, "")
    assert t == 100 and "v1.35" in basis
    assert idle_window([{"release": "v1.37", "released_at": 300}]) == (
        300,
        "released_at of v1.37 (start of the v1.37 cycles)",
    )
    assert idle_window([]) is None


def test_automation_labels() -> None:
    pred = automation_label_predicate()
    for prefix in ("tracked/", "size/", "cncf-cla"):
        assert f"c.field STARTS WITH '{prefix}'" in pred, prefix
    for name in ("lgtm", "approved"):
        assert f"c.field = '{name}'" in pred, name
    assert "$" not in pred and pred.startswith("(") and pred.endswith(")")
    assert "'stage/" not in pred and "'approved-api'" not in pred
    assert automation_label_predicate("e.name").count("e.name") == 5


def test_new_tools_registered_on_every_surface() -> None:
    for name in ("why_designed", "contested_points", "knowledge_risk"):
        assert name in {t.name for t in llm_tools()}
        assert name in {t.name for t in mcp_tools()}
