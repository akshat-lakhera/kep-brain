"""Split a KEP README into `Section`s with GitHub-compatible anchors (03 §4.2, recon D8).

A section starts at every `##` heading; a `##` block larger than 6 KB that
contains `###` headings is split further at `###`. Headings inside fenced code
blocks are ignored. Anchors follow GitHub's slugger: lower-case, punctuation
removed, spaces to hyphens, duplicates suffixed `-1`, `-2` in document order
over all headings (any level), exactly as the rendered page links them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

SPLIT_THRESHOLD_BYTES = 6 * 1024
SUMMARY_MAX_CHARS = 2000

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Ordered: first match wins (more specific phrases before generic ones).
_KIND_RULES: tuple[tuple[str, str], ...] = (
    ("non-goals", "non_goals"),
    ("non goals", "non_goals"),
    ("production readiness review questionnaire", "prr_questionnaire"),
    ("production readiness", "prr_questionnaire"),
    ("implementation history", "implementation_history"),
    ("graduation criteria", "graduation_criteria"),
    ("upgrade / downgrade", "upgrade_downgrade"),
    ("upgrade/downgrade", "upgrade_downgrade"),
    ("version skew", "version_skew"),
    ("design details", "design_details"),
    ("drawbacks", "drawbacks"),
    ("alternatives", "alternatives"),
    ("motivation", "motivation"),
    ("summary", "summary"),
    ("goals", "goals"),
    ("proposal", "proposal"),
)


def heading_text(raw: str) -> str:
    """Rendered text of a Markdown heading: links -> text, code/emphasis markers and HTML tags dropped."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", raw)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "")
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    return text.strip()


def slugify(text: str) -> str:
    """GitHub heading slug (github-slugger): keep letters, digits, marks, `-`, `_` and spaces."""
    out = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if ch in "-_ " or cat[0] in "LNM":
            out.append(ch)
    return "".join(out).replace(" ", "-")


class Slugger:
    """Deduplicates slugs the way GitHub does (`x`, `x-1`, `x-2`, skipping taken ones)."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}

    def slug(self, text: str) -> str:
        base = slugify(text)
        candidate = base
        while candidate in self.seen:
            self.seen[base] += 1
            candidate = f"{base}-{self.seen[base]}"
        self.seen[candidate] = 0
        return candidate


def classify(heading: str) -> str:
    low = heading.lower().strip()
    for needle, kind in _KIND_RULES:
        if needle in low:
            return kind
    return "other"


def scrub(text: str) -> str:
    """Remove e-mail addresses (03 §9)."""
    return _EMAIL_RE.sub("[email removed]", text)


@dataclass(frozen=True)
class Heading:
    line: int
    level: int
    text: str
    anchor: str


@dataclass(frozen=True)
class ParsedSection:
    anchor: str
    heading: str
    level: int
    order: int
    text: str
    kind: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def headings(markdown: str) -> list[Heading]:
    """Every ATX heading outside fenced code, with its deduplicated anchor."""
    slugger = Slugger()
    found: list[Heading] = []
    fence: str | None = None
    for i, line in enumerate(markdown.splitlines()):
        fm = _FENCE_RE.match(line)
        if fm:
            marker = fm.group(1)
            if fence is None:
                fence = marker[0] * 3
            elif marker.startswith(fence):
                fence = None
            continue
        if fence is not None:
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            text = heading_text(hm.group(2))
            found.append(Heading(line=i, level=len(hm.group(1)), text=text, anchor=slugger.slug(text)))
    return found


def split_sections(markdown: str) -> list[ParsedSection]:
    lines = markdown.splitlines()
    heads = headings(markdown)
    bounds: list[tuple[Heading, int]] = []  # (heading, end line exclusive)
    level2 = [h for h in heads if h.level <= 2]
    for idx, h in enumerate(level2):
        if h.level != 2:
            continue
        end = level2[idx + 1].line if idx + 1 < len(level2) else len(lines)
        block = "\n".join(lines[h.line + 1 : end])
        subs = [s for s in heads if s.level == 3 and h.line < s.line < end]
        if len(block.encode("utf-8")) > SPLIT_THRESHOLD_BYTES and subs:
            bounds.append((h, subs[0].line))
            for j, sub in enumerate(subs):
                bounds.append((sub, subs[j + 1].line if j + 1 < len(subs) else end))
        else:
            bounds.append((h, end))
    sections: list[ParsedSection] = []
    for order, (h, end) in enumerate(bounds):
        body = scrub("\n".join(lines[h.line + 1 : end]).strip())
        sections.append(
            ParsedSection(anchor=h.anchor, heading=h.text, level=h.level, order=order, text=body, kind=classify(h.text))
        )
    return sections


def doc_sections(markdown: str, fallback_title: str) -> tuple[str, list[ParsedSection]]:
    """Title and sections of a stand-alone document (a process or product README, not a KEP).

    The definition lives under the `#` title, before the first `##`; `split_sections` keeps only `##` sections and
    a table of contents says nothing, so the opening text becomes section 0 (kind `summary`) and the table of
    contents is dropped. Orders are renumbered over what is kept.
    """
    heads = headings(markdown)
    h1 = next((h for h in heads if h.level == 1), None)
    title = h1.text if h1 else fallback_title
    parsed = [s for s in split_sections(markdown) if s.heading.strip().lower() != "table of contents"]
    if h1:
        lines = markdown.splitlines()
        first = next((h.line for h in heads if h.level <= 2 and h.line > h1.line), len(lines))
        intro = scrub("\n".join(lines[h1.line + 1 : first]).strip())
        if intro:
            parsed.insert(
                0, ParsedSection(anchor=h1.anchor, heading=h1.text, level=1, order=0, text=intro, kind="summary")
            )
    return title, [
        ParsedSection(anchor=s.anchor, heading=s.heading, level=s.level, order=i, text=s.text, kind=s.kind)
        for i, s in enumerate(parsed)
    ]


def summary_text(sections: list[ParsedSection]) -> str | None:
    for s in sections:
        if s.kind == "summary" and s.level == 2 and s.text:
            return s.text[:SUMMARY_MAX_CHARS]
    return None
