"""`draft_stale_doc_issue`: the draft asks which record is current and marks the fix as unverified."""

from __future__ import annotations

from typing import Any

from app.db.falkordb import QueryOutput
from app.tools.base import ToolContext
from app.tools.t01.draft_issue import DraftStaleDocIssue

KEP_KEY = "keps/sig-scheduling/583-coscheduling"
FND_KEY = f"fnd:active_status_closed_issue:{KEP_KEY}"
FINDING = {
    "label": "Finding", "key": FND_KEY, "kind": "active_status_closed_issue", "a_label": "kep.yaml status",
    "a_value": "provisional", "a_url": "https://a", "b_label": "issue #583 state",
    "b_value": "closed (reason not recorded) on 2019-09-09", "b_url": "https://b", "suggested_fix": "review_status",
}  # fmt: skip
KEP = {"label": "KEP", "key": KEP_KEY, "number": 583, "url": "https://k"}


class OneRowPool:
    async def ro_query(self, graph: str, query: str, params: Any = None, timeout_ms: int = 0) -> QueryOutput:
        header = ["finding", "kep", "tracking_issue", "kep_yaml", "evidence"]
        return QueryOutput(header, [[FINDING, KEP, [], [], []]], 0.0, {})


async def test_draft_title_and_body_wording() -> None:
    result = await DraftStaleDocIssue().invoke(ToolContext(pool=OneRowPool()), {"finding_key": FND_KEY})  # type: ignore[arg-type]
    draft = result.rows[0]
    assert draft["posted"] is False and draft["status"] == "drafted"
    assert draft["title"] == (
        "KEP-583: kep.yaml and tracking issue disagree (active status closed issue); "
        "please confirm which record is current"
    )
    assert "Possible fix (unverified): review_status" in draft["body"]
    assert "Suggested fix:" not in draft["body"]
    assert "- **kep.yaml status**: provisional (https://a)" in draft["body"]
