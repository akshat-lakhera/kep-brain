"""The tool registry (06 C2): one catalog for the planner, `/v1/tools` and MCP."""

from __future__ import annotations

from app.errors import AppError
from app.tools.base import Tool
from app.tools.schema_tool import GetGraphSchema
from app.tools.t01.changed_since import ChangedSince
from app.tools.t01.decision_path import PathToDecision
from app.tools.t01.draft_issue import DraftStaleDocIssue
from app.tools.t01.graph_algos import PathBetween, RankPeople
from app.tools.t01.impact import ImpactOfChange
from app.tools.t01.who_knows import WhoKnows
from app.tools.t02.memory_findings import RecallFindings, RecallMemory
from app.tools.t03.audit import FindContradictions, KepRelations
from app.tools.t03.find_entities import FindEntities
from app.tools.t03.get_kep import GetKep
from app.tools.t03.history import StatusHistory, TraceDecision, WhatsChanged
from app.tools.t03.who import WhoApproves, WhoOwns

_ALL: tuple[Tool, ...] = (
    FindEntities(),
    GetKep(),
    WhoApproves(),
    WhoOwns(),
    TraceDecision(),
    StatusHistory(),
    WhatsChanged(),
    FindContradictions(),
    KepRelations(),
    PathBetween(),
    RankPeople(),
    WhoKnows(),
    ImpactOfChange(),
    PathToDecision(),
    ChangedSince(),
    RecallMemory(),
    RecallFindings(),
    DraftStaleDocIssue(),
    GetGraphSchema(),
)

TOOLS: dict[str, Tool] = {t.name: t for t in _ALL}


def llm_tools() -> list[Tool]:
    """The LLM-callable tools (planner, `/v1/tools`)."""
    return [t for t in _ALL if t.llm_callable]


def mcp_tools() -> list[Tool]:
    """The MCP tools: LLM catalog minus recall_memory and the draft action, plus get_graph_schema."""
    return [t for t in _ALL if t.on_mcp]


def get_tool(name: str, *, llm_only: bool = True) -> Tool:
    tool = TOOLS.get(name)
    if tool is None or (llm_only and not tool.llm_callable):
        raise AppError("tool_not_found", {"name": name[:80]})
    return tool
