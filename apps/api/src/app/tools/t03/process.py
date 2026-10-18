"""`explain_process`: what a KEP is and how the process works, read from the process documents in the graph.

`sync-docs` stores `keps/README.md` and the KEP process KEP from kubernetes/enhancements as
`Document {kind: 'process'}` nodes with their sections (`app.ingest.docs.PROCESS_DOCS`), and the product
document (what KEP Brain itself is) as `Document {kind: 'product'}` (`app.ingest.product`). This tool
returns each process document's opening section (the definition), the product document's opening when the
topic is about KEP Brain itself, and then the sections of either kind that match the topic, so a question
such as "what is a KEP" or "what is KEP Brain" is answered from the record and cited, never from a model's
memory.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult

EXCERPT_CHARS = 900
ROWS = 8

# The full-text index ANDs every word and keeps stopwords, so a question such as "explain me what kep is"
# matches nothing until it becomes an OR of its content words ("kep*").
_FILLER = frozenset(
    (
        "a", "an", "and", "are", "be", "can", "could", "do", "does", "explain", "for", "from", "how", "i", "in",
        "is", "it", "its", "me", "mean", "means", "of", "on", "or", "please", "tell", "that", "the", "this", "to",
        "us", "was", "what", "when", "where", "which", "who", "why", "will", "with", "you",
    )
)  # fmt: skip


# Obvious misspellings of the product's name, normalised so the term matches the product document ("kp brain",
# "kepbrain"). Each value is one or more index words.
_ALIASES: dict[str, tuple[str, ...]] = {
    "kp": ("kep",),
    "kpe": ("kep",),
    "ekp": ("kep",),
    "kepbrain": ("kep", "brain"),
    "kpbrain": ("kep", "brain"),
}
_PRODUCT_RE = re.compile(r"brain|this (?:tool|product|app|site)", re.I)


def is_product_topic(topic: str) -> bool:
    """True when the topic asks about KEP Brain itself rather than the KEP process."""
    return _PRODUCT_RE.search(topic) is not None


def topic_term(topic: str) -> str | None:
    """`"what is a KEP"` → `"kep*"`; `"status implementable"` → `"status*|implementable*"`; only filler → None.

    `"what is kp brain"` → `"kep*|brain*"`: aliases in `_ALIASES` are rewritten first.
    """
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", topic)]
    words = [v for w in words for v in _ALIASES.get(w, (w,))]
    keep = [w for w in words if w not in _FILLER and len(w) >= 2]
    if not keep:
        return None
    return "|".join(f"{w}*" if len(w) >= 3 else w for w in dict.fromkeys(keep))


OPENING = """
MATCH (d:Document {kind: 'process'})-[:HAS_SECTION]->(s:Section)
WHERE s.order = 0 AND toLower(s.heading) <> 'table of contents'
RETURN d AS document, s AS section, s.text AS text, 1.0 AS score
ORDER BY d.path
LIMIT 4
"""

PRODUCT_OPENING = """
MATCH (d:Document {kind: 'product'})-[:HAS_SECTION]->(s:Section)
WHERE s.order = 0
RETURN d AS document, s AS section, s.text AS text, 1.0 AS score
ORDER BY d.path
LIMIT 2
"""

SEARCH = """
CALL db.idx.fulltext.queryNodes('Section', $term) YIELD node AS s, score
MATCH (d:Document)-[:HAS_SECTION]->(s)
WHERE d.kind IN ['process', 'product'] AND toLower(s.heading) <> 'table of contents'
RETURN d AS document, s AS section, s.text AS text, score
ORDER BY score DESC, s.order
LIMIT 8
"""


class ExplainProcessParams(ToolParams):
    topic: str = Field(
        min_length=2,
        max_length=160,
        description=(
            "What to explain, e.g. 'what is a KEP', 'status implementable', 'production readiness review', "
            "'superseded-by'"
        ),
    )


class ExplainProcess(Tool):
    name = "explain_process"
    description = (
        "What a KEP is, how the KEP process works, and what KEP Brain itself is and does. Read from the documents "
        "stored in the graph: the process documents of kubernetes/enhancements (keps/README.md and the KEP process "
        "KEP: the kep.yaml fields and what they mean, the statuses and stages, the tracking issue, PRR, replaces and "
        "superseded-by) and the KEP Brain product document (what it answers, how answers are produced and checked, "
        "the audit, data sources, privacy, licence). Returns each document's opening section plus the sections "
        "matching the topic, as citable records. Use for 'what is a KEP', 'what does status X mean', 'how does the "
        "process work', 'what is KEP Brain'."
    )
    Params = ExplainProcessParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: ExplainProcessParams = params
        run = Run(ctx)
        opening = await run.query(OPENING, {}, limit=4)
        if is_product_topic(p.topic):
            opening += await run.query(PRODUCT_OPENING, {}, limit=2)
        term = topic_term(p.topic)
        hits = await run.query(SEARCH, {"term": term}, limit=ROWS) if term else []
        seen = {r["section"]["key"] for r in opening}
        rows = opening + [h for h in hits if h["section"]["key"] not in seen]
        out: list[dict[str, Any]] = []
        for r in rows[:ROWS]:
            text = str(r.get("text") or "")
            out.append(
                {
                    "document": r["document"],
                    "section": r["section"],
                    "excerpt": text[:EXCERPT_CHARS] + ("…" if len(text) > EXCERPT_CHARS else ""),
                    "score": r.get("score"),
                }
            )
            run.add_path(r["document"]["key"], "HAS_SECTION", r["section"]["key"])
        summary = {"topic": p.topic, "term": term, "opening_sections": len(opening), "matching_sections": len(hits)}
        return run.result([summary, *out])
