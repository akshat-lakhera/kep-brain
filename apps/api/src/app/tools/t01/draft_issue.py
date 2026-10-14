"""Tool 26 `draft_stale_doc_issue` (03 §15.2): compose an issue draft from a Finding.

Pure: it reads the finding, its KEP, the tracking issue and the evidence
records, and returns a draft whose body lists every evidence item with its
URL. It never posts anything; posting is a separate human-confirmed action.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.tools.base import Run, Tool, ToolContext, ToolParams, ToolResult

TEMPLATE = """
MATCH (f:Finding {key: $finding_key})
MATCH (k:KEP {key: f.kep_path})
RETURN f AS finding, k AS kep,
 [(k)-[r:TRACKED_BY]->(i:Issue) WHERE coalesce(r.valid_to, $open) = $open | i] AS tracking_issue,
 [(k)-[r:HAS_DOCUMENT]->(d:Document) WHERE d.kind = 'kep_yaml' | d] AS kep_yaml,
 [(f)-[r:EVIDENCED_BY]->(e) | {node: e, evidence_kind: r.evidence_kind}] AS evidence
LIMIT 1
"""

DEFAULT_TARGET_REPO = "kubernetes/enhancements"


class DraftStaleDocIssueParams(ToolParams):
    finding_key: str = Field(pattern=r"^fnd:[a-z_]+:keps/[A-Za-z0-9/._:-]+$", max_length=400)


def _line(item: dict[str, Any]) -> str:
    return f"- {item.get('label', '')} `{item.get('key', '')}` → {item.get('url', '')}"


class DraftStaleDocIssue(Tool):
    name = "draft_stale_doc_issue"
    description = (
        "Draft (never post) an issue asking to fix a KEP's stale or contradictory metadata, from a Finding key "
        "(fnd:<kind>:<KEP path>). The draft lists both disagreeing sides and every evidence record with its URL "
        "and the suggested fix. A human must review and confirm before anything is posted."
    )
    Params = DraftStaleDocIssueParams
    on_mcp = False

    async def run(self, ctx: ToolContext, params: Any) -> ToolResult:
        p: DraftStaleDocIssueParams = params
        run = Run(ctx)
        rows = await run.query(TEMPLATE, {"finding_key": p.finding_key}, limit=2)
        if not rows:
            return run.result([{"finding_key": p.finding_key, "not_found": True}])
        row = rows[0]
        f, kep = row["finding"], row["kep"]
        number = kep.get("number")
        name = f"KEP-{number}" if number is not None else kep["key"]
        title = f"{name}: kep.yaml metadata disagrees with its sources ({f.get('kind', '').replace('_', ' ')})"
        evidence = [kep, *row.get("tracking_issue", []), *row.get("kep_yaml", [])]
        evidence += [e["node"] for e in row.get("evidence", [])]
        seen: set[str] = set()
        lines = []
        for item in evidence:
            if item.get("key") and item["key"] not in seen and item.get("url"):
                seen.add(item["key"])
                lines.append(_line(item))
        body = "\n".join(
            [
                f"`{kep['key']}` has two sources that disagree.",
                "",
                f"- **{f.get('a_label', 'Side A')}**: {f.get('a_value', '')} ({f.get('a_url', '')})",
                f"- **{f.get('b_label', 'Side B')}**: {f.get('b_value', '')} ({f.get('b_url', '')})",
                "",
                f"Suggested fix: {f.get('suggested_fix', 'review the metadata')}",
                "",
                "Evidence:",
                *lines,
            ]
        )
        draft = {
            "finding_key": p.finding_key,
            "title": title,
            "body": body,
            "target_repo": DEFAULT_TARGET_REPO,
            "status": "drafted",
            "posted": False,
            "evidence_keys": sorted(seen),
        }
        run.add_path(p.finding_key, "ABOUT", kep["key"])
        return run.result([draft, row])
