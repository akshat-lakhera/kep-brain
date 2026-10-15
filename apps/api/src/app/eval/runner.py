"""Eval runner: `python -m app.eval run --arms G,N --questions judge --reps 1 --max-usd 2`.

Arm G is the full graph agent (`app.agent.loop.Agent`, answer cache off); arm N is the same model with no tools and no
sources, whose uncited answers the validator rule turns into `unsupported_claims`. Rows are scored deterministically by
`app.eval.scoring`; citation validity and contradiction recall come from the graph (`app.eval.graphcheck`). Calls run
one at a time (the LLM free tier is rate limited) and wait up to BATCH_MAX_WAIT_S for a model's quota; a run stops at
`--max-usd` or at the first `provider_rate_limited`, and a stopped or crashed run continues with `--resume`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from ulid import ULID

from app.agent.loop import Agent
from app.agent.prompts import ABSTAIN_PREFIX
from app.agent.provider import Provider, cost_usd, llm_configured, make_provider
from app.agent.validator import parse_answer
from app.db.falkordb import FalkorPool
from app.errors import AppError
from app.eval.graphcheck import contradiction_recall, load_reference, resolved_citations
from app.eval.questions import evals_dir, judge_questions, load_questions, run_dirs
from app.eval.scoring import summarise
from app.settings import Settings, get_settings

log = structlog.get_logger(__name__)

ARMS = ("G", "N")
SEED = 42
MAX_CONSECUTIVE_ERRORS = 5
N_PROMPT = (
    "You answer questions about Kubernetes Enhancement Proposals (KEPs) from memory only. No tools, documents or "
    f"sources are available. If you cannot answer with certainty, reply with the line '{ABSTAIN_PREFIX} no_evidence'. "
    "Otherwise reply with a short answer."
)
# A batch run waits this long for a model's quota (Groq's daily token quota refills continuously) before the provider
# gives up with provider_rate_limited; the run then stops instead of burning the remaining questions.
BATCH_MAX_WAIT_S = 900.0
# Quota waits count against the agent's wall-clock budget, so a batch ask gets room for several of them.
BATCH_WALL_BUDGET_S = 3600.0
STOP_CODES = frozenset({"provider_rate_limited", "llm_not_configured"})
SCORING = (
    "Pass = not abstained and every expected evidence key cited (any_of group and required node labels where "
    "recorded); ABS questions pass on an accepted abstain_reason. Questions with expected_evidence 'unknown' are "
    "unscored. Fact lists and set equality are not judged by this scorer."
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _citations(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"key": c.get("key"), "label": c.get("label"), "url": c.get("url")} for c in raw]


async def ask_graph(agent: Agent, question: str) -> dict[str, Any]:
    started = time.perf_counter()
    out = await agent.ask(question, request_id=str(ULID()))
    calls = out.get("tool_calls", [])
    usage = out.get("usage", {})
    model = out.get("model") or agent.settings.llm_model
    return {
        "abstained": out["abstained"],
        "abstain_reason": out.get("abstain_reason"),
        "answer_markdown": out.get("answer_markdown", ""),
        "citations": _citations(out.get("citations", [])),
        "tools": [c["name"] for c in calls],
        "tools_ms": round(sum(c.get("ms") or 0 for c in calls), 1),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_usd": cost_usd(model, usage.get("input_tokens", 0), usage.get("output_tokens", 0)),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "model": model,
    }


async def ask_alone(provider: Provider, question: str) -> dict[str, Any]:
    started = time.perf_counter()
    turn = await provider.complete([{"role": "system", "content": N_PROMPT}, {"role": "user", "content": question}], [])
    final = parse_answer(turn.text)
    attempted = not final.abstained and bool(final.answer_markdown)
    model = getattr(provider, "last_model", provider.model)
    return {
        "abstained": True,
        "abstain_reason": "unsupported_claims" if attempted else (final.abstain_reason or "no_evidence"),
        "answer_markdown": final.answer_markdown[:2000] if attempted else "",
        "citations": [],
        "tools": [],
        "tools_ms": 0.0,
        "input_tokens": turn.input_tokens,
        "output_tokens": turn.output_tokens,
        "cost_usd": cost_usd(model, turn.input_tokens, turn.output_tokens),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "model": model,
    }


def select_questions(questions: list[dict[str, Any]], which: str) -> list[dict[str, Any]]:
    if which == "judge":
        return judge_questions(questions)
    ordered = list(questions)
    random.Random(SEED).shuffle(ordered)
    return ordered


def build_summary(
    run_id: str,
    meta: dict[str, Any],
    questions: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    errors: int,
    resolved: set[tuple[str, str]] | None = None,
    contradictions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agg = summarise(questions, rows, resolved)
    g = agg["overall"].get("G")
    n = agg["overall"].get("N")
    return {
        "run_id": run_id,
        **meta,
        "questions": len({r["qid"] for r in rows}),
        "rows": len(rows),
        "errors": errors,
        "cost_usd": round(sum(r.get("cost_usd") or 0.0 for r in rows), 6),
        "scoring": SCORING,
        "overall": agg["overall"],
        "by_kind": agg["by_kind"],
        "per_question": agg["per_question"],
        "latency_by_stage": (
            {"total_p50_ms": g["latency_p50_ms"], "total_p95_ms": g["latency_p95_ms"],
             "graph_tools_p50_ms": g["tools_p50_ms"], "graph_tools_p95_ms": g["tools_p95_ms"]}
            if g else None
        ),
        "baseline": (
            {"arm": "N (no tools, no sources)", "scored": n["scored"], "passed": n["passed"], "accuracy": n["accuracy"],
             "validator_rescues": n["validator_rescues"]}
            if n else None
        ),
        "contradiction_recall": contradictions,
    }  # fmt: skip


def _write_summary(run: Path, summary: dict[str, Any]) -> None:
    (run / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _open_run(resume: str | None) -> tuple[str, Path, dict[str, Any]]:
    root = evals_dir() / "runs"
    if resume:
        dirs = run_dirs(root)
        if resume == "latest":
            partial = [d for d in dirs if not _is_complete(d)]
            if not partial:
                raise SystemExit("no partial run to resume")
            run = partial[-1]
        else:
            run = root / resume
            if not run.is_dir():
                raise SystemExit(f"run {resume} not found")
        meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
        return run.name, run, meta
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = root / run_id
    run.mkdir(parents=True)
    return run_id, run, {}


def _is_complete(run: Path) -> bool:
    summary = run / "summary.json"
    return summary.is_file() and bool(json.loads(summary.read_text(encoding="utf-8")).get("complete"))


async def run_eval(args: argparse.Namespace, settings: Settings) -> int:
    arms = [a.strip().upper() for a in args.arms.split(",") if a.strip()]
    if not set(arms) <= set(ARMS):
        print(f"unknown arm in {arms}; available: {', '.join(ARMS)}", file=sys.stderr)
        return 2
    if not llm_configured(settings):
        print("LLM is not configured: set OPENAI_API_KEY (apps/api/.env)", file=sys.stderr)
        return 2
    all_questions = load_questions()
    by_id = {q["id"]: q for q in all_questions}
    chosen = select_questions(all_questions, args.questions)
    if not chosen:
        print("no questions selected", file=sys.stderr)
        return 2

    run_id, run, meta = _open_run(args.resume)
    meta = meta or {
        "created_at": _now(), "arms": arms, "reps": args.reps, "question_set": args.questions,
        "model": settings.llm_model, "pin": settings.enhancements_pin_sha, "max_usd": args.max_usd,
    }  # fmt: skip
    (run / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    results, errors = run / "results.jsonl", run / "errors.jsonl"
    rows = _read_jsonl(results)
    done = {(r["arm"], r["qid"], r["rep"]) for r in rows}
    spent = sum(r.get("cost_usd") or 0.0 for r in rows)
    plan = [(rep, q, arm) for rep in range(1, meta["reps"] + 1) for q in chosen for arm in meta["arms"]]
    todo = [p for p in plan if (p[2], p[1]["id"], p[0]) not in done]
    print(f"run {run_id}: {len(todo)} calls to make, {len(done)} already recorded, ${spent:.4f} spent")

    pool = FalkorPool(settings)
    provider = make_provider(settings, max_wait_s=BATCH_MAX_WAIT_S)
    agent = Agent(pool, settings, provider, use_cache=False, wall_budget_s=BATCH_WALL_BUDGET_S)
    stopped: str | None = None
    consecutive = 0
    try:
        for i, (rep, q, arm) in enumerate(todo, 1):
            if spent >= args.max_usd:
                stopped = "max_usd"
                break
            try:
                out = await (
                    ask_graph(agent, q["question"]) if arm == "G" else ask_alone(agent.provider, q["question"])
                )
            except Exception as exc:  # noqa: BLE001 - one failed call is recorded, not fatal
                code = exc.code if isinstance(exc, AppError) else type(exc).__name__
                _append(
                    errors,
                    {"arm": arm, "qid": q["id"], "rep": rep, "class": code, "at": _now(), "message": str(exc)[:300]},
                )
                consecutive += 1
                print(f"[{i}/{len(todo)}] {arm} {q['id']} error {code}")
                if code in STOP_CODES:
                    stopped = code
                    break
                if consecutive >= MAX_CONSECUTIVE_ERRORS:
                    stopped = f"{consecutive} consecutive errors"
                    break
                continue
            consecutive = 0
            row = {"arm": arm, "qid": q["id"], "rep": rep, **out}
            _append(results, row)
            rows.append(row)
            spent += out["cost_usd"]
            verdict = summarise({q["id"]: q}, [row])["per_question"][0]["passed"]
            print(f"[{i}/{len(todo)}] {arm} {q['id']} passed={verdict} abstained={out['abstained']} ${spent:.4f}")
            _write_summary(
                run, build_summary(run_id, {**meta, "complete": False}, by_id, rows, len(_read_jsonl(errors)))
            )
        complete = stopped is None
        final = {**meta, "complete": complete, "stopped": stopped, "finished_at": _now()}
        resolved = await resolved_citations(pool, rows)
        contradictions = await contradiction_recall(pool, load_reference(Path(args.con_reference)))
        _write_summary(
            run, build_summary(run_id, final, by_id, rows, len(_read_jsonl(errors)), resolved, contradictions)
        )
    finally:
        pool.close()
    print(f"run {run_id} {'complete' if complete else 'stopped: ' + str(stopped)}; ${spent:.4f}")
    return 0 if complete else 1


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        f"Run {summary['run_id']}: {summary['rows']} rows, {summary['errors']} errors, ${summary['cost_usd']:.4f}"
        + ("" if summary.get("complete") else f" (incomplete: {summary.get('stopped') or 'in progress'})"),
        "",
        "| Arm | Kind | n | Scored | Passed | Accuracy | False abstentions | Rescues |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in summary["by_kind"].values():
        lines.append(
            f"| {g['arm']} | {g['kind']} | {g['n']} | {g['scored']} | {g['passed']} | {_pct(g['accuracy'])} "
            f"| {g['false_abstentions']} | {g['validator_rescues']} |"
        )
    for arm, g in summary["overall"].items():
        lines.append(
            f"| {arm} | all | {g['n']} | {g['scored']} | {g['passed']} | {_pct(g['accuracy'])} "
            f"| {g['false_abstentions']} | {g['validator_rescues']} |"
        )
    lines.append("")
    for arm, g in summary["overall"].items():
        lines.append(
            f"{arm}: citation validity {_pct(g.get('citation_validity'))} of {g.get('citations', 0)} citations; "
            f"citation recall {_pct(g.get('citation_recall'))}; abstention precision "
            f"{_pct(g.get('abstention_precision'))}, recall {_pct(g.get('abstention_recall'))}"
        )
    con = summary.get("contradiction_recall") or {}
    if con.get("available"):
        lines.append(f"Contradiction recall vs reference: {con['found']}/{con['reference']} ({_pct(con['recall'])})")
    return "\n".join(lines)


def report(run_id: str | None) -> int:
    root = evals_dir() / "runs"
    dirs = [root / run_id] if run_id else list(reversed(run_dirs(root)))
    for d in dirs:
        if (d / "summary.json").is_file():
            print(render_report(json.loads((d / "summary.json").read_text(encoding="utf-8"))))
            return 0
    print("no run with a summary.json", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval", description="KEP Brain evaluation runner")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="ask the questions and score the answers")
    run.add_argument("--arms", default="G", help="comma list of G (graph agent), N (no tools)")
    run.add_argument("--questions", choices=["all", "judge"], default="judge")
    run.add_argument("--reps", type=int, default=1)
    run.add_argument("--max-usd", type=float, default=2.0)
    run.add_argument("--resume", nargs="?", const="latest", help="continue a run by id (default: newest partial run)")
    run.add_argument(
        "--con-reference",
        default=str(evals_dir().parent / ".recon" / "eval" / "contradiction-counts.json"),
        help="reference contradiction hits for the contradiction-recall measure",
    )
    rep = sub.add_parser("report", help="print a markdown table for a run")
    rep.add_argument("--run", default=None, help="run id (default: newest with a summary)")
    args = parser.parse_args(argv)
    if args.command == "report":
        return report(args.run)
    return asyncio.run(run_eval(args, get_settings()))
