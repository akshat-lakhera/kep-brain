"""Planner prompt and tool specs for the agent loop (02 §6.1)."""

from __future__ import annotations

import copy
import re
from typing import Any

from app.tools.base import Tool

# The answer is the assistant's plain-text reply, not tool-call arguments: on Groq, qwen cuts every string
# argument of a tool call at about 500 characters (measured 2026-10-15), which truncated answers mid-word.
ABSTAIN_PREFIX = "ABSTAIN:"

SYSTEM_PROMPT = f"""\
You are KEP Brain. Answer questions about the Kubernetes KEPs held in the graph ONLY from tool \
results; never from outside knowledge. Call every tool the question needs in ONE round (parallel calls, \
including every KEP the question names), then answer; a second round only if the rows are insufficient. \
Pass a KEP number as kep_ref.
Routes: status/metadata current -> find_contradictions + get_kep, then report every disagreement they return. \
Replaces / what became of -> kep_relations \
(mode=lineage). When/by whom/which PR -> trace_decision with kinds (e.g. [status_transition]); reversals -> \
status_history. Person to KEP -> path_between, who_approves. Feature gate -> find_entities(kinds=[FeatureGate,KEP]).
Answer: reply with concise Markdown text (no tool call); dates YYYY-MM-DD, KEP-<n>, @login. Put \
[[evidence_id]] (12 chars, from tool rows) right after every factual sentence or list item; never invent ids or \
URLs. Findings carry no evidence_id; for a disagreement cite the record on each side instead (the kep.yaml \
document or KEP, and the tracking issue or the successor KEP).
Abstain by starting the reply with the line "{ABSTAIN_PREFIX} no_evidence" (or "{ABSTAIN_PREFIX} out_of_scope"), \
then explain with citations:
- no_exact_match or only match='nearest' rows: the thing asked about does not exist in the graph; say there is \
no exact match and name the nearest entity. Never present it as the answer.
- a match='historical' feature gate is declared by no current kep.yaml: say which KEP formerly declared it and \
when (formerly_declared_by), and which gate that KEP declares now.
- outside the three SIGs: out_of_scope. No relevant rows: no_evidence.
"""
WRITE_NOW = "Tool budget reached. Write the answer now as Markdown text with [[evidence_id]] citations."


def _resolve_refs(schema: Any, defs: dict[str, Any]) -> Any:
    if isinstance(schema, dict):
        if "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[-1]
            return _resolve_refs(copy.deepcopy(defs.get(name, {})), defs)
        return {k: _resolve_refs(v, defs) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_resolve_refs(v, defs) for v in schema]
    return schema


def _simplify(schema: Any) -> Any:
    """Reduce a Pydantic JSON schema to the subset every function-calling provider accepts."""
    if isinstance(schema, list):
        return [_simplify(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    s = dict(schema)
    if "anyOf" in s:
        branches = [b for b in s.pop("anyOf") if b.get("type") != "null"]
        if len(branches) == 1:
            merged = {**branches[0], **{k: v for k, v in s.items() if k in ("description", "default")}}
            return _simplify(merged)
        s["type"] = "string"
    for drop in ("title", "$defs", "additionalProperties", "default", "pattern", "maxLength", "minLength"):
        s.pop(drop, None)
    if "const" in s:
        s["enum"] = [s.pop("const")]
    if "enum" in s and s.get("type") != "string":
        values = s.pop("enum")
        note = "one of " + ", ".join(str(v) for v in values)
        s["description"] = f"{s.get('description', '')} ({note})".strip()
        if "type" not in s and values:
            s["type"] = "integer" if isinstance(values[0], int) else "string"
    if s.get("type") == "object":
        s["properties"] = {k: _simplify(v) for k, v in s.get("properties", {}).items()}
    if "items" in s:
        s["items"] = _simplify(s["items"])
    for bound in ("minimum", "maximum"):
        if bound in s:
            s["description"] = f"{s.get('description', '')} ({bound} {s.pop(bound)})".strip()
    s.pop("maxItems", None)
    return s


# Tool specs are resent on every turn; short descriptions keep each request inside a
# tokens-per-minute budget on rate-limited providers.
SPEC_DESCRIPTION_CHARS = 100
PARAM_DESCRIPTION_CHARS = 40


_SENTENCE_END = re.compile(r"(?<!e\.g)(?<!i\.e)\.\s")
# Optional knobs the planner never needs; the tools' defaults apply.
_PLANNER_DROPS = frozenset({"limit", "path_count"})
# Tools the planner never calls: the draft action, and memory recall unless the request carries a memory id.
NOT_FOR_PLANNER = frozenset({"draft_stale_doc_issue"})
MEMORY_TOOL = "recall_memory"


def brief(text: str, limit: int = SPEC_DESCRIPTION_CHARS) -> str:
    """The first sentence, cut at a word boundary when it is still longer than `limit`."""
    m = _SENTENCE_END.search(text)
    first = text[: m.start() + 1] if m else text
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0]
    if cut.count("(") > cut.count(")"):
        cut = cut[: cut.rfind("(")]
    return cut.rstrip(" ,;:")


def tool_spec(tool: Tool) -> dict[str, Any]:
    raw = tool.params_schema()
    resolved = _resolve_refs(raw, raw.get("$defs", {}))
    params = _simplify(resolved)
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    required = set(params.get("required", []))
    for name in _PLANNER_DROPS - required:
        params["properties"].pop(name, None)
    for prop in params["properties"].values():
        if isinstance(prop, dict) and "description" in prop:
            prop["description"] = brief(prop["description"], PARAM_DESCRIPTION_CHARS)
    return {"type": "function", "function": {"name": tool.name, "description": brief(tool.description),
                                              "parameters": params}}  # fmt: skip
