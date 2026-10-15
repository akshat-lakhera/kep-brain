"""`why_designed`: the KEP's own rationale, read from its README sections (03 §4.2).

The README is stored as `Section` nodes (one per `##` heading; large `##` blocks are split at `###`).
Goals, Non-Goals and Risks and Mitigations are usually `###` headings inside the Motivation and
Proposal sections, so they are cut out of the section text here. Their anchors are recomputed with
GitHub's slugger over every heading of the README in document order (the stored section headings
plus the headings inside their text), which is how the rendered page links them.

Every row is an excerpt (at most `EXCERPT_CHARS` characters) with the GitHub URL of its heading,
plus the KEPs this one replaces and is replaced by.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ingest.sections import Slugger, classify, headings
from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult
from app.tools.kepref import KepRef, resolve_kep, unresolved_rows

EXCERPT_CHARS = 1200
# A section's own text before its first sub-heading is used when it says enough on its own.
MIN_INTRO_CHARS = 200

# Rationale parts in answer order. `drawbacks` covers "Drawbacks" and "Risks and Mitigations".
PARTS: tuple[str, ...] = (
    "summary", "motivation", "goals", "non_goals", "proposal", "alternatives", "drawbacks", "risks",
)  # fmt: skip

SECTIONS = """
MATCH (k:KEP {key: $key})-[:HAS_DOCUMENT]->(d:Document {kind: 'kep_readme'})-[:HAS_SECTION]->(s:Section)
RETURN s AS section, d.key AS doc_key, s.text AS text, s.level AS level, s.order AS order, s.anchor AS anchor,
 s.heading AS heading, s.url AS url
ORDER BY s.order
LIMIT 200
"""

CUR = "coalesce(r.valid_to, $open) = $open"

RELATIONS = f"""
MATCH (k:KEP {{key: $key}})
RETURN k AS kep,
 [(k)-[r:REPLACES]->(o:KEP) WHERE {CUR} | {{kep: o, declared_by: r.declared_by}}] AS replaces,
 [(o:KEP)-[r:REPLACES]->(k) WHERE {CUR} | {{kep: o, declared_by: r.declared_by}}] AS replaced_by,
 [(k)-[r:SUPERSEDED_BY]->(o:KEP) WHERE {CUR} | {{kep: o, derived: r.derived}}] AS superseded_by
LIMIT 1
"""


@dataclass(frozen=True)
class Block:
    """One heading of the README with the text under it (up to the next heading of any level)."""

    heading: str
    anchor: str
    url: str
    level: int
    intro: str
    full: str
    section_key: str


def part_of(heading: str) -> str | None:
    low = heading.lower()
    if "risk" in low and "mitigation" in low:
        return "risks"
    kind = classify(heading)
    return kind if kind in PARTS else None


def _base_url(url: str) -> str:
    return url.split("#", 1)[0]


def section_blocks(sections: list[dict[str, Any]]) -> list[Block]:
    """Blocks for every stored section and every heading inside its text, anchors deduplicated document-wide."""
    slugger = Slugger()
    out: list[Block] = []
    for sec in sections:
        text = str(sec.get("text") or "")
        heading = str(sec.get("heading") or "")
        stored_anchor = str(sec.get("anchor") or "")
        slugger.slug(heading)
        url = str(sec.get("url") or "")
        inner = headings(text)
        lines = text.splitlines()
        first = inner[0].line if inner else len(lines)
        out.append(
            Block(
                heading=heading,
                anchor=stored_anchor,
                url=url,
                level=int(sec.get("level") or 2),
                intro="\n".join(lines[:first]).strip(),
                full=text.strip(),
                section_key=str(sec.get("key") or ""),
            )
        )
        for i, h in enumerate(inner):
            anchor = slugger.slug(h.text)
            # Text up to the next heading at the same or a higher level.
            end = next((n.line for n in inner[i + 1 :] if n.level <= h.level), len(lines))
            nxt = inner[i + 1].line if i + 1 < len(inner) else len(lines)
            out.append(
                Block(
                    heading=h.text,
                    anchor=anchor,
                    url=f"{_base_url(url)}#{anchor}",
                    level=h.level,
                    intro="\n".join(lines[h.line + 1 : nxt]).strip(),
                    full="\n".join(lines[h.line + 1 : end]).strip(),
                    section_key=str(sec.get("key") or ""),
                )
            )
    return out


def excerpt(block: Block) -> tuple[str, int]:
    """(excerpt, length of the source text): the block's intro when long enough, else its whole text."""
    source = block.intro if len(block.intro) >= MIN_INTRO_CHARS else block.full
    return source[:EXCERPT_CHARS].rstrip(), len(source)


def pick_parts(blocks: list[Block]) -> dict[str, Block]:
    """The first block per rationale part, preferring the highest heading level (## over ###)."""
    found: dict[str, Block] = {}
    for block in sorted(blocks, key=lambda b: b.level):
        part = part_of(block.heading)
        if part is None or part in found:
            continue
        if not block.full:
            # A split `## Proposal` keeps no text of its own: use its first plain sub-section instead.
            child = _first_child(blocks, block) if part == "proposal" else None
            if child is not None:
                found[part] = child
            continue
        found[part] = block
    return found


def _first_child(blocks: list[Block], parent: Block) -> Block | None:
    start = blocks.index(parent)
    for block in blocks[start + 1 :]:
        if block.level <= parent.level:
            return None
        if block.full and part_of(block.heading) is None:
            return block
    return None


class WhyDesignedParams(ToolParams):
    kep_ref: KepRef


class WhyDesigned(Tool):
    name = "why_designed"
    description = (
        "Why a KEP was designed the way it is, from its README: Summary, Motivation, Goals, Non-Goals, the "
        "Proposal's opening, Alternatives considered, Drawbacks and Risks and Mitigations, each as an excerpt "
        "(<=1200 chars) with the GitHub URL of its heading, plus the KEPs it replaces and is replaced by. Use for "
        "'why was X done', 'what was rejected', 'what are the known risks'. Parts the README lacks are listed "
        "as missing."
    )
    Params = WhyDesignedParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: WhyDesignedParams = params
        run = Run(ctx)
        res = await resolve_kep(run, p.kep_ref)
        if res.key is None:
            return run.result(unresolved_rows(p.kep_ref, res))
        rel = await run.query(RELATIONS, {"key": res.key}, limit=2)
        secs = await run.query(SECTIONS, {"key": res.key}, limit=200)
        run.truncated = False
        sections = [{**r, "key": r["section"]["key"]} for r in secs]
        evidence_ids = {r["section"]["key"]: r["section"].get("evidence_id") for r in secs}
        chosen = pick_parts(section_blocks(sections))
        rows: list[dict[str, Any]] = []
        for part in PARTS:
            block = chosen.get(part)
            if block is None:
                continue
            text, chars = excerpt(block)
            rows.append(
                {
                    "part": part,
                    "heading": block.heading,
                    "url": block.url,
                    "excerpt": text,
                    "chars": chars,
                    "truncated": chars > len(text),
                    "section_key": block.section_key,
                    "evidence_id": evidence_ids.get(block.section_key),
                }
            )
        doc_keys = {r["section"]["key"]: r.get("doc_key") for r in secs}
        for row in rows:
            run.add_path(
                res.key, "HAS_DOCUMENT", str(doc_keys.get(row["section_key"]) or ""), "HAS_SECTION", row["section_key"]
            )
        relations = rel[0] if rel else {}
        kep = relations.get("kep") or res.candidates[0]
        for r in relations.get("replaces", []):
            run.add_path(res.key, "REPLACES", r["kep"]["key"])
        for r in relations.get("replaced_by", []):
            run.add_path(r["kep"]["key"], "REPLACES", res.key)
        for r in relations.get("superseded_by", []):
            run.add_path(res.key, "SUPERSEDED_BY", r["kep"]["key"])
        summary = {
            "kep": {k: kep[k] for k in ("key", "number", "title", "status", "url", "evidence_id") if k in kep},
            "parts_found": [r["part"] for r in rows],
            "parts_missing": [part for part in PARTS if part not in chosen],
            "replaces": relations.get("replaces", []),
            "replaced_by": relations.get("replaced_by", []),
            "superseded_by": relations.get("superseded_by", []),
            "url": kep.get("url"),
        }
        return run.result([summary, *rows])
