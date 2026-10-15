"""Deterministic scoring (04 §6.2, §7): cited keys against expected evidence, and abstention correctness.

Only what the question file records is checked. A question whose `expected_evidence` is `unknown` cannot be scored
by citations and is reported as unscored rather than guessed. Facts, set equality and judge-checked clauses are out
of scope for this scorer.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any


def _cites(cited: set[str], expected: str) -> bool:
    return expected in cited or any(c.startswith(expected + "#") for c in cited)


def _evidence_keys(items: Any) -> list[str] | None:
    if not isinstance(items, list):
        return None
    return [i["key"] for i in items if isinstance(i, dict) and i.get("key")]


def score_row(question: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """`passed` is True/False, or None when the question cannot be scored from citations."""
    cited = {c["key"] for c in row.get("citations", []) if c.get("key")}
    labels = {c["label"] for c in row.get("citations", []) if c.get("label")}
    abstained = bool(row.get("abstained"))
    reason = row.get("abstain_reason")
    out: dict[str, Any] = {"passed": None, "false_abstention": False, "rescue": False, "recall": None}

    if question.get("kind") == "ABS":
        accept = question.get("accept") or []
        if abstained:
            out["passed"] = reason in accept or reason == "unsupported_claims"
            out["rescue"] = reason == "unsupported_claims"
        elif question.get("accept_explicit_negative"):
            named = _evidence_keys(question.get("explicit_negative_evidence"))
            out["passed"] = named is not None and len(named) > 0 and all(_cites(cited, k) for k in named)
        else:
            out["passed"] = False
        return out

    if abstained:
        out.update(passed=False, false_abstention=True)
        return out
    expected = _evidence_keys(question.get("expected_evidence"))
    if expected is None:
        return out
    hits = [k for k in expected if _cites(cited, k)]
    out["recall"] = len(hits) / len(expected) if expected else None
    ok = len(hits) == len(expected)
    any_of = _evidence_keys(question.get("expected_evidence_any"))
    if any_of:
        ok = ok and any(_cites(cited, k) for k in any_of)
    required = question.get("require_any_label")
    if required:
        ok = ok and bool(labels & set(required))
    out["passed"] = ok
    return out


def first_tool_hit(question: dict[str, Any], row: dict[str, Any]) -> bool | None:
    expected = question.get("expected_tools")
    tools = row.get("tools") or []
    if not isinstance(expected, dict) or not tools:
        return None
    return bool(tools[0] == expected.get("first"))


def wilson(passed: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = passed / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1)]


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _group(rows: list[dict[str, Any]], resolved: set[tuple[str, str]] | None = None) -> dict[str, Any]:
    scored = [r for r in rows if r["passed"] is not None]
    passed = sum(1 for r in scored if r["passed"])
    answerable = [r for r in rows if r["kind"] != "ABS"]
    recalls = [r["recall"] for r in rows if r["recall"] is not None]
    ci = wilson(passed, len(scored))
    abstentions = [r for r in rows if r.get("abstained")]
    abs_rows = [r for r in rows if r["kind"] == "ABS"]
    correct_abstentions = sum(1 for r in abs_rows if r.get("abstained") and r["passed"])
    cited = [(c.get("label"), c.get("key")) for r in rows for c in r.get("citations") or []]
    return {
        "n": len(rows),
        "scored": len(scored),
        "unscored": len(rows) - len(scored),
        "passed": passed,
        "accuracy": round(passed / len(scored), 4) if scored else None,
        "ci95": list(ci) if ci else None,
        "false_abstentions": sum(1 for r in rows if r["false_abstention"]),
        "false_abstention_rate": (
            round(sum(1 for r in answerable if r["false_abstention"]) / len(answerable), 4) if answerable else None
        ),
        "validator_rescues": sum(1 for r in rows if r["rescue"]),
        "citation_recall": round(statistics.fmean(recalls), 4) if recalls else None,
        "citations": len(cited),
        "citation_validity": None if resolved is None else _rate(sum(1 for c in cited if c in resolved), len(cited)),
        "abstentions": len(abstentions),
        "abstention_precision": _rate(correct_abstentions, len(abstentions)),
        "abstention_recall": _rate(correct_abstentions, len(abs_rows)),
    }


def summarise(
    questions: dict[str, dict[str, Any]], rows: list[dict[str, Any]], resolved: set[tuple[str, str]] | None = None
) -> dict[str, Any]:
    """Aggregates over result rows; every figure is recomputed from the rows and the question file. `resolved` holds
    the cited (label, key) pairs found in the graph; without it citation validity is not reported."""
    flat: list[dict[str, Any]] = []
    for row in rows:
        q = questions.get(row["qid"])
        if q is None:
            continue
        flat.append({**row, "kind": q.get("kind"), **score_row(q, row), "first_tool_hit": first_tool_hit(q, row)})

    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_arm_kind: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in flat:
        by_arm[r["arm"]].append(r)
        by_arm_kind[(r["arm"], str(r["kind"]))].append(r)

    overall = {}
    for arm, items in by_arm.items():
        hits = [r["first_tool_hit"] for r in items if r["first_tool_hit"] is not None]
        totals = [r["latency_ms"] for r in items if r.get("latency_ms") is not None]
        tool_ms = [r["tools_ms"] for r in items if r.get("tools_ms") is not None]
        overall[arm] = {
            **_group(items, resolved),
            "first_tool_hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
            "cost_usd": round(sum(r.get("cost_usd") or 0.0 for r in items), 6),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in items),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in items),
            "latency_p50_ms": percentile(totals, 50),
            "latency_p95_ms": percentile(totals, 95),
            "tools_p50_ms": percentile(tool_ms, 50),
            "tools_p95_ms": percentile(tool_ms, 95),
        }
    by_kind = {
        f"{arm}/{kind}": {"arm": arm, "kind": kind, **_group(items, resolved)}
        for (arm, kind), items in sorted(by_arm_kind.items())
    }
    per_question = [
        {
            "arm": r["arm"],
            "id": r["qid"],
            "kind": r["kind"],
            "rep": r["rep"],
            "passed": r["passed"],
            "abstained": r.get("abstained"),
            "abstain_reason": r.get("abstain_reason"),
            "citations": len(r.get("citations", [])),
            "tools": len(r.get("tools") or []),
            "latency_ms": r.get("latency_ms"),
            "cost_usd": r.get("cost_usd"),
        }
        for r in flat
    ]
    return {"overall": overall, "by_kind": by_kind, "per_question": per_question}
