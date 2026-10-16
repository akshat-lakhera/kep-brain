"""Tool 1 `find_entities`: resolve free text to graph entities (03 §15.1).

Exact matches first (KEP number, Person login, SIG key, FeatureGate name,
ticket number), then the full-text indexes per requested label. When nothing
matches exactly, the nearest-match mode splits identifier-like input
(`GangScheduling` → `Gang Scheduling`) and searches KEP titles and gate names,
so a caller can say "no exact match; nearest is …" instead of guessing.
"""

from __future__ import annotations

import re
from typing import Any, Literal

import structlog
from pydantic import Field
from redis.exceptions import ResponseError

from app.ingest.common import normalise_login
from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult

log = structlog.get_logger(__name__)

Kind = Literal["KEP", "Person", "SIG", "FeatureGate", "Issue", "PullRequest", "Section"]
ALL_KINDS: tuple[Kind, ...] = ("KEP", "Person", "SIG", "FeatureGate", "Issue", "PullRequest", "Section")


class FindEntitiesParams(ToolParams):
    query: str = Field(min_length=2, max_length=200, description="Free text: a KEP number, name, login, gate…")
    kinds: list[Kind] = Field(default_factory=list, description="Labels to search; empty means all")
    limit: Literal[5, 10, 20] = 10


_NUM = re.compile(r"^(?:kep[-\s#]?|#)?0*(\d{1,6})$", re.IGNORECASE)
_TICKET = re.compile(r"^(?:kubernetes/enhancements)?#(\d{1,6})$")
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9]+$")

_KEP_EXTRA = """
 [(node)-[g:GATED_BY]->(fg:FeatureGate) WHERE coalesce(g.valid_to, $open) = $open | fg.name] AS gates,
 [(node)-[o:OWNED_BY]->(s:SIG) WHERE coalesce(o.valid_to, $open) = $open | s.key] AS sigs"""

# A gate row says which KEPs declare it now and which declared it in the past
# (closed GATED_BY intervals from git history), so a renamed gate is not mistaken
# for a current one.
_GATE_EXTRA = """
 [(k:KEP)-[g:GATED_BY]->(node) WHERE coalesce(g.valid_to, $open) = $open | k] AS keps,
 [(k:KEP)-[g:GATED_BY]->(node) WHERE g.valid_to <> $open
   | {kep: k, declared_from: g.valid_from_iso, declared_until: g.valid_to_iso, source_url: g.source_url}]
   AS formerly_declared_by"""

EXACT = {
    "KEP": f"MATCH (node:KEP {{number: $number}}) RETURN node, 1.0 AS score,{_KEP_EXTRA} ORDER BY node.key LIMIT 10",
    "Person": "MATCH (node:Person {key: $login}) RETURN node, 1.0 AS score LIMIT 1",
    "SIG": "MATCH (node:SIG {key: $sig}) RETURN node, 1.0 AS score LIMIT 1",
    "FeatureGate": f"MATCH (node:FeatureGate {{key: $gate}}) RETURN node, 1.0 AS score,{_GATE_EXTRA} LIMIT 1",
    "Issue": "MATCH (node:Issue {key: $ticket}) RETURN node, 1.0 AS score LIMIT 1",
    "PullRequest": "MATCH (node:PullRequest {key: $ticket}) RETURN node, 1.0 AS score LIMIT 1",
}


def _fulltext(label: str, limit: int) -> str:
    extra = ""
    if label == "KEP":
        extra = "," + _KEP_EXTRA
    elif label == "FeatureGate":
        extra = "," + _GATE_EXTRA
    return (
        f"CALL db.idx.fulltext.queryNodes('{label}', $term) YIELD node, score\n"
        f"RETURN node, score{extra}\n"
        f"ORDER BY score DESC, node.key\n"
        f"LIMIT {limit}"
    )


FULLTEXT = {(label, n): _fulltext(label, n) for label in ALL_KINDS for n in (5, 10, 20)}


def fulltext_term(text: str, prefix: bool = True) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    if not tokens:
        return None
    if prefix and len(tokens[-1]) >= 3:
        tokens[-1] = tokens[-1] + "*"
    return " ".join(tokens)


def split_identifier(text: str) -> str:
    """`GangScheduling` → `Gang Scheduling`; `InPlacePodVerticalScaling` → `In Place Pod Vertical Scaling`."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text)


class FindEntities(Tool):
    name = "find_entities"
    description = (
        "Resolve free text to graph entities: KEPs (by number, title or summary), people (GitHub login), SIGs, "
        "feature gates, issues, pull requests and README sections. Exact key matches come first (match='exact'), "
        "then full-text hits (match='fulltext'). If nothing matches exactly, identifier-like input is split into "
        "words and searched again (match='nearest'): a nearest match is NOT the thing asked for, only the closest "
        "existing entity. match='historical' means a feature gate that no kep.yaml declares any more; its "
        "formerly_declared_by lists which KEP declared it and when. KEP rows include their current feature gates "
        "and owning SIG. Use this first to get keys."
    )
    Params = FindEntitiesParams

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: FindEntitiesParams = params
        run = Run(ctx)
        kinds = p.kinds or list(ALL_KINDS)
        q = p.query.strip()
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(found: list[dict[str, Any]], match: str) -> None:
            for r in found:
                node = r.pop("node")
                if node["key"] in seen:
                    continue
                seen.add(node["key"])
                rows.append({"match": match, "score": round(float(r.pop("score") or 0), 3), **node, **r})

        num = _NUM.match(q)
        ticket = _TICKET.match(q)
        if num and "KEP" in kinds:
            add(await run.query(EXACT["KEP"], {"number": int(num.group(1))}, limit=10), "exact")
        if ticket:
            for label in ("Issue", "PullRequest"):
                if label in kinds:
                    key = f"kubernetes/enhancements#{int(ticket.group(1))}"
                    add(await run.query(EXACT[label], {"ticket": key}, limit=1), "exact")
        if "Person" in kinds:
            add(await run.query(EXACT["Person"], {"login": normalise_login(q) or q.lower()}, limit=1), "exact")
        if "SIG" in kinds:
            add(await run.query(EXACT["SIG"], {"sig": q.lower().replace(" ", "-")}, limit=1), "exact")
        if "FeatureGate" in kinds:
            gates = await run.query(EXACT["FeatureGate"], {"gate": q}, limit=1)
            current = [g for g in gates if g.get("keps")]
            add(current, "exact")
            # A gate no kep.yaml declares any more is history, not a current match.
            add([g for g in gates if not g.get("keps")], "historical")
        exact_found = any(r.get("match") == "exact" for r in rows)

        term = fulltext_term(q)
        if term and not (num and exact_found):
            for label in kinds:
                add(await self._search(run, label, term, p.limit), "fulltext")

        if not exact_found and _IDENT.match(q):
            words = split_identifier(q)
            nearest_term = fulltext_term(words, prefix=False)
            if nearest_term and words != q:
                for label in ("KEP", "FeatureGate"):
                    add(await self._search(run, label, nearest_term, p.limit), "nearest")
                first = fulltext_term(words.split(" ")[0])
                if first:
                    add(await self._search(run, "FeatureGate", first, p.limit), "nearest")
        if not exact_found:
            rows.insert(0, {"no_exact_match": q})
        run.truncated = len(rows) > p.limit * len(kinds)
        return run.result(rows)

    async def _search(self, run: Run, label: str, term: str, limit: int) -> list[dict[str, Any]]:
        try:
            return await run.query(FULLTEXT[(label, limit)], {"term": term}, limit=limit + 1)  # type: ignore[index]
        except ResponseError as exc:  # missing index or a term made only of stopwords
            log.info("fulltext_skipped", label=label, error=str(exc)[:120])
            return []
