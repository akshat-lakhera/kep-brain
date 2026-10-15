"""Eval measures that need the graph (04 §7, §9.1): citation validity and contradiction recall against the reference
re-implementation of the five predicates. No LLM involved."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.db.falkordb import GRAPH_KEP, FalkorPool
from app.schema.labels import NODE_LABELS

RESOLVE = "UNWIND $keys AS k MATCH (n:{label} {{key: k}}) RETURN n.key"
FINDINGS = "MATCH (f:Finding) WHERE f.state <> 'dismissed' RETURN f.kind, f.key"


async def resolved_citations(pool: FalkorPool, rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """The (label, key) pairs cited in `rows` that exist as nodes in the graph."""
    by_label: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for c in row.get("citations") or []:
            if c.get("label") in NODE_LABELS and c.get("key"):
                by_label[c["label"]].add(c["key"])
    found: set[tuple[str, str]] = set()
    for label, keys in by_label.items():
        out = await pool.ro_query(GRAPH_KEP, RESOLVE.format(label=label), {"keys": sorted(keys)})
        found.update((label, r[0]) for r in out.rows)
    return found


def _reference_hits(reference: dict[str, Any]) -> list[tuple[str, frozenset[str]]]:
    hits = []
    for kind, items in (reference.get("hits") or {}).items():
        if kind.startswith("_"):  # tracked by the reference script but not one of the five kinds
            continue
        for item in items:
            keps = frozenset(v for k, v in item.items() if k in ("kep", "predecessor", "successor"))
            if keps:
                hits.append((kind, keps))
    return hits


def load_reference(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


async def contradiction_recall(pool: FalkorPool, reference: dict[str, Any] | None) -> dict[str, Any]:
    """Share of the reference hits (kind + KEP keys) that the product's open Findings also flag."""
    if reference is None:
        return {"available": False, "reason": "reference hits file not found"}
    out = await pool.ro_query(GRAPH_KEP, FINDINGS)
    # Finding keys are fnd:<kind>:<KEP key>[:<successor key>]; KEP keys hold no colon.
    product: dict[str, list[set[str]]] = defaultdict(list)
    for kind, key in out.rows:
        product[kind].append(set(key.split(":")[2:]))

    def flagged(kind: str, keps: frozenset[str]) -> bool:
        return any(keps <= flagged_keps for flagged_keps in product.get(kind, []))

    by_kind: dict[str, dict[str, Any]] = {}
    for kind, keps in _reference_hits(reference):
        g = by_kind.setdefault(kind, {"reference": 0, "found": 0, "missed": []})
        g["reference"] += 1
        if flagged(kind, keps):
            g["found"] += 1
        else:
            g["missed"].append(sorted(keps))
    for g in by_kind.values():
        g["recall"] = round(g["found"] / g["reference"], 4)
    total = sum(g["reference"] for g in by_kind.values())
    found = sum(g["found"] for g in by_kind.values())
    return {
        "available": True,
        "method": "product Findings vs the reference script's hits on the pinned files (04 §9.1); "
        "not the human blind-sample recall",
        "reference_generated_at": reference.get("generated_at"),
        "reference": total,
        "found": found,
        "recall": round(found / total, 4) if total else None,
        "product_findings": sum(len(v) for v in product.values()),
        "by_kind": by_kind,
    }
