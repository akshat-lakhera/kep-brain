"""Tool contract (06 C2, 03 §15).

A tool is a name, a one-paragraph description, a Pydantic `Params` model with
bounded ranges, and fixed Cypher templates (one per limit variant; parameters
never reach `LIMIT`). Every template runs through `FalkorPool.ro_query`
(`GRAPH.RO_QUERY`, 2000 ms). Results are projected to `ToolResult` with an
evidence entry for every keyed node they contain.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from falkordb import Edge, Node, Path
from pydantic import BaseModel, ConfigDict, Field

from app.db.falkordb import GRAPH_KEP, MAX_ROWS, READ_TIMEOUT_MS, FalkorPool
from app.db.results import Evidence, evidence_id, node_title, primary_label
from app.schema.labels import VALID_TO_OPEN
from app.tools.cypher import unique_comprehension_vars

# Properties shown per label in tool rows. Everything a tool returns is a
# projection of these, so the LLM context stays small and stable.
_FIELDS: dict[str, tuple[str, ...]] = {
    "KEP": (
        "number", "title", "owning_sig", "status", "stage", "latest_milestone", "milestone_alpha",
        "milestone_beta", "milestone_stable", "creation_date", "last_updated", "metadata_invalid",
    ),
    "Person": ("login", "is_bot"),
    "SIG": ("display_name", "label", "in_scope"),
    "WorkingGroup": ("display_name",),
    "Committee": ("display_name",),
    "Issue": (
        "number", "title", "state", "state_reason", "created_at_iso", "closed_at_iso", "labels_current",
        "milestone_current", "is_tracking_issue",
    ),
    "PullRequest": ("number", "title", "state", "merged_at_iso", "merged_by_login", "author_login"),
    "StatusChange": (
        "kind", "kep_path", "field", "op", "from_value", "to_value", "at_iso", "actor_login", "is_reversal",
        "commit_sha",
    ),
    "Decision": (
        "kind", "kep_path", "summary", "decided_at_iso", "human_decider", "from_value", "to_value", "stage",
    ),
    "Finding": (
        "kind", "kep_path", "state", "a_label", "a_value", "a_url", "b_label", "b_value", "b_url",
        "suggested_fix", "detected_at_iso", "triage_verdict", "assessment",
    ),
    "Commit": ("sha", "authored_at_iso", "subject", "pr_number"),
    "Review": ("state", "author_login", "submitted_at_iso"),
    "Comment": ("author_login", "created_at_iso", "commands"),
    "Release": ("name", "is_future"),
    "FeatureGate": ("name",),
    "Document": ("kind", "path"),
    "Section": ("kep_path", "heading", "anchor", "kind"),
    "Label": ("name",),
}  # fmt: skip

# Findings and memory are context, never evidence (02 §6.2 item 5): their rows carry no
# evidence_id, so a planner cannot cite them; the validator rejects them as well.
NON_EVIDENCE_LABELS = frozenset({"Finding", "Episode", "Fact"})

_EDGE_FIELDS = ("stage", "role", "position", "declared_by", "derived", "raw", "evidence_kind", "valid_from_iso")


class ToolResult(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    paths: list[list[str]] = Field(default_factory=list)
    truncated: bool = False
    ms: float = 0.0
    template: str = ""


class ToolParams(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


@dataclass
class ToolContext:
    pool: FalkorPool
    graph: str = GRAPH_KEP
    memory_id: str | None = None


@dataclass
class Projector:
    """Turns FalkorDB values into compact rows, collecting evidence on the way."""

    evidence: dict[str, Evidence] = field(default_factory=dict)
    _ids: dict[int, str] = field(default_factory=dict)

    def node(self, node: Node) -> dict[str, Any]:
        props = node.properties or {}
        label = primary_label(node)
        key = str(props.get("key", ""))
        url = str(props.get("url") or props.get("source_url") or "")
        out: dict[str, Any] = {"label": label, "key": key, "title": node_title(label, props), "url": url}
        if key:
            eid = evidence_id(label, key)
            if label not in NON_EVIDENCE_LABELS:
                out["evidence_id"] = eid
            if node.id is not None:
                self._ids[node.id] = key
            self.evidence.setdefault(eid, Evidence(evidence_id=eid, label=label, key=key, title=out["title"], url=url))
        for name in _FIELDS.get(label, ()):
            value = props.get(name)
            if value is not None and value != "" and value != []:
                # A node property must not overwrite the node label (SIG.label is the
                # GitHub label name, e.g. "scheduling"; it is projected as sig_label).
                out[f"{label.lower()}_label" if name == "label" else name] = value
        return out

    def edge(self, edge: Edge) -> dict[str, Any]:
        props = edge.properties or {}
        out: dict[str, Any] = {"type": edge.relation}
        for name in _EDGE_FIELDS:
            if props.get(name) is not None:
                out[name] = props[name]
        if props.get("valid_to") is not None:
            out["current"] = props["valid_to"] == VALID_TO_OPEN
        return out

    def path(self, path: Path) -> list[str]:
        nodes = path.nodes()
        out: list[str] = []
        for i, n in enumerate(nodes):
            self.node(n)
            out.append(str((n.properties or {}).get("key", "")))
            if i < len(path.edges()):
                out.append(path.edges()[i].relation)
        return out

    def value(self, value: Any) -> Any:
        if isinstance(value, Node):
            return self.node(value)
        if isinstance(value, Edge):
            return self.edge(value)
        if isinstance(value, Path):
            return self.path(value)
        if isinstance(value, list):
            return [self.value(v) for v in value if v is not None]
        if isinstance(value, dict):
            return {k: self.value(v) for k, v in value.items() if v is not None}
        return value


@dataclass
class Run:
    """Accumulates the queries of one tool call into one `ToolResult`."""

    ctx: ToolContext
    projector: Projector = field(default_factory=Projector)
    templates: list[str] = field(default_factory=list)
    paths: list[list[str]] = field(default_factory=list)
    truncated: bool = False
    started: float = field(default_factory=time.perf_counter)

    async def query(
        self, template: str, params: dict[str, Any] | None = None, *, limit: int = MAX_ROWS
    ) -> list[dict[str, Any]]:
        """Run one fixed template; `limit` is the template's own fixed LIMIT (for the truncation flag)."""
        merged = {"open": VALID_TO_OPEN, **(params or {})}
        template = unique_comprehension_vars(template)
        out = await self.ctx.pool.ro_query(self.ctx.graph, template, merged, timeout_ms=READ_TIMEOUT_MS)
        self.templates.append(_normalise(template))
        rows = [dict(zip(out.header, (self.projector.value(v) for v in row), strict=False)) for row in out.rows]
        if len(rows) >= limit:
            self.truncated = True
        return rows[:MAX_ROWS]

    def add_path(self, *parts: str) -> None:
        if all(parts):
            self.paths.append(list(parts))

    def result(self, rows: list[dict[str, Any]]) -> ToolResult:
        return ToolResult(
            rows=rows[:MAX_ROWS],
            evidence=list(self.projector.evidence.values()),
            paths=self.paths[:MAX_ROWS],
            truncated=self.truncated or len(rows) > MAX_ROWS,
            ms=round((time.perf_counter() - self.started) * 1000, 1),
            template="\n;\n".join(dict.fromkeys(self.templates)),
        )


def _normalise(template: str) -> str:
    return re.sub(r"[ \t]+", " ", template.strip())


class Tool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    Params: ClassVar[type[ToolParams]]
    # Surfaces (03 §15, 02 §7.2): MCP never gets recall_memory or the draft action.
    on_mcp: ClassVar[bool] = True
    llm_callable: ClassVar[bool] = True

    @abstractmethod
    async def run(self, ctx: ToolContext, params: Any) -> ToolResult: ...

    async def invoke(self, ctx: ToolContext, raw: dict[str, Any]) -> ToolResult:
        params = self.Params.model_validate(raw)
        return await self.run(ctx, params)

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        return cls.Params.model_json_schema()
