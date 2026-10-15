"""Eval runner stop rules, graph-backed measures and the extra summary rates (no LLM, no FalkorDB)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.agent.provider import Turn
from app.db.falkordb import QueryOutput
from app.errors import AppError
from app.eval import runner
from app.eval.graphcheck import contradiction_recall, resolved_citations
from app.eval.scoring import summarise
from app.settings import Settings

KEP583 = "keps/sig-scheduling/583-coscheduling"
KEP4671 = "keps/sig-scheduling/4671-gang-scheduling"
QUESTIONS = [
    {"id": "STA-04", "kind": "STA", "question": "What is the status of KEP-583?", "judge_order": 1,
     "expected_evidence": [{"label": "KEP", "key": KEP583}]},
    {"id": "ABS-10", "kind": "ABS", "question": "Which KEP introduced the GangScheduling gate?", "judge_order": 2,
     "accept": ["no_evidence"]},
    {"id": "MH-07", "kind": "MH", "question": "How is soltysh connected to KEP-4671?", "judge_order": 3,
     "expected_evidence": [{"label": "KEP", "key": KEP4671}]},
]  # fmt: skip


class FakePool:
    def __init__(self, findings: list[tuple[str, str]] | None = None, nodes: set[tuple[str, str]] | None = None):
        self.findings = findings or []
        self.nodes = nodes or set()

    async def ro_query(self, graph: str, query: str, params: Any = None, timeout_ms: int = 0) -> QueryOutput:
        if "Finding" in query:
            return QueryOutput(["kind", "key"], [list(f) for f in self.findings], 0.0, {})
        label = query.split("(n:", 1)[1].split(" ", 1)[0]
        return QueryOutput(["key"], [[k] for k in params["keys"] if (label, k) in self.nodes], 0.0, {})

    def close(self) -> None:
        return None


def g_row(qid: str, citations: list[tuple[str, str]], abstained: bool = False, reason: str | None = None) -> dict:
    return {"arm": "G", "qid": qid, "rep": 1, "abstained": abstained, "abstain_reason": reason,
            "citations": [{"label": lb, "key": k} for lb, k in citations]}  # fmt: skip


def test_summary_reports_abstention_precision_recall_and_citation_validity() -> None:
    questions = {q["id"]: q for q in QUESTIONS}
    rows = [
        g_row("STA-04", [("KEP", KEP583), ("Issue", "kubernetes/enhancements#999999")]),
        g_row("ABS-10", [("KEP", KEP4671)], True, "no_evidence"),
        g_row("MH-07", [], True, "no_evidence"),
    ]
    resolved = {("KEP", KEP583), ("KEP", KEP4671)}
    g = summarise(questions, rows, resolved)["overall"]["G"]
    assert (g["citations"], g["citation_validity"]) == (3, round(2 / 3, 4))
    assert (g["abstentions"], g["abstention_precision"], g["abstention_recall"]) == (2, 0.5, 1.0)
    assert summarise(questions, rows)["overall"]["G"]["citation_validity"] is None


async def test_resolved_citations_checks_each_label_against_the_graph() -> None:
    pool = FakePool(nodes={("KEP", KEP583)})
    rows = [g_row("STA-04", [("KEP", KEP583), ("KEP", "keps/x/1-missing"), ("NotALabel", KEP583)])]
    assert await resolved_citations(pool, rows) == {("KEP", KEP583)}  # type: ignore[arg-type]


async def test_contradiction_recall_matches_kind_and_every_kep_of_a_hit() -> None:
    reference = {
        "generated_at": "2026-10-12T03:19:55Z",
        "hits": {
            "active_status_closed_issue": [{"kep": KEP583}, {"kep": "keps/sig-node/1-x"}],
            "one_sided_replacement": [{"predecessor": KEP583, "successor": KEP4671}],
            "_in_flight_stage_drift": [{"kep": KEP4671}],
        },
    }
    pool = FakePool(findings=[
        ("active_status_closed_issue", f"fnd:active_status_closed_issue:{KEP583}"),
        ("one_sided_replacement", f"fnd:one_sided_replacement:{KEP583}:{KEP4671}"),
        ("stage_mismatch", f"fnd:stage_mismatch:{KEP583}"),
    ])  # fmt: skip
    out = await contradiction_recall(pool, reference)  # type: ignore[arg-type]
    assert (out["reference"], out["found"], out["recall"], out["product_findings"]) == (3, 2, round(2 / 3, 4), 3)
    assert out["by_kind"]["active_status_closed_issue"]["missed"] == [["keps/sig-node/1-x"]]
    assert "_in_flight_stage_drift" not in out["by_kind"]
    assert (await contradiction_recall(pool, None))["available"] is False  # type: ignore[arg-type]


class QuotaAgent:
    """Answers the first question, then hits the provider's daily quota."""

    calls = 0
    model = "m"

    def __init__(self, pool: Any, settings: Settings, *_: Any, **__: Any) -> None:
        self.settings = settings
        self.provider = self

    async def ask(self, question: str, request_id: str) -> dict[str, Any]:
        QuotaAgent.calls += 1
        if QuotaAgent.calls > 1:
            raise AppError("provider_rate_limited")
        citations = [{"label": "KEP", "key": KEP583, "index": 1}]
        return {"abstained": False, "citations": citations, "tool_calls": [], "model": "m",
                "usage": {"input_tokens": 10, "output_tokens": 5}, "answer_markdown": "x [1]"}  # fmt: skip

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
        return Turn(text="ABSTAIN: no_evidence")


async def test_run_stops_on_the_provider_quota_and_keeps_partial_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "questions.yaml").write_text(yaml.safe_dump({"questions": QUESTIONS}), encoding="utf-8")
    monkeypatch.setenv("EVALS_DIR", str(tmp_path))
    monkeypatch.setattr(runner, "FalkorPool", lambda settings: FakePool(nodes={("KEP", KEP583)}))
    monkeypatch.setattr(runner, "Agent", QuotaAgent)
    monkeypatch.setattr(runner, "make_provider", lambda settings, max_wait_s: None)
    monkeypatch.setattr(runner, "llm_configured", lambda settings: True)
    QuotaAgent.calls = 0
    args = argparse.Namespace(arms="G", questions="judge", reps=1, max_usd=2.0, resume=None,
                              con_reference=str(tmp_path / "missing.json"))  # fmt: skip
    assert await runner.run_eval(args, Settings()) == 1
    run = next((tmp_path / "runs").iterdir())
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    assert summary["complete"] is False and summary["stopped"] == "provider_rate_limited"
    assert summary["rows"] == 1 and summary["errors"] == 1 and QuotaAgent.calls == 2
    assert summary["overall"]["G"]["citation_validity"] == 1.0
    assert summary["contradiction_recall"]["available"] is False
    errors = [json.loads(line) for line in (run / "errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["class"] for e in errors] == ["provider_rate_limited"]


async def test_baseline_arm_reads_the_text_protocol() -> None:
    out = await runner.ask_alone(QuotaAgent(None, Settings()), "Which KEP introduced X?")  # type: ignore[arg-type]
    assert out["abstained"] and out["abstain_reason"] == "no_evidence" and out["answer_markdown"] == ""
