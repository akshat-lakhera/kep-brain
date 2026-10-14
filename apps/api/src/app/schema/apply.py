"""Create the indexes and constraints of a `kep`-shaped graph (03 §12.2, §13).

Idempotent: an index or constraint that already exists is reported as
`exists` and counts as success. Order follows 03 §13: range indexes, full-text
indexes, then UNIQUE constraints (which need the exact-match index first),
then a poll until every constraint is `OPERATIONAL`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from redis.exceptions import ResponseError

from app.db.falkordb import WRITE_TIMEOUT_MS, FalkorPool, Role
from app.schema.labels import NODE_LABELS

log = structlog.get_logger(__name__)

# Secondary range indexes used by tools (03 §12.2).
SECONDARY_RANGE: tuple[tuple[str, str], ...] = (
    ("KEP", "number"),
    ("KEP", "owning_sig"),
    ("KEP", "status"),
    ("Finding", "kep_path"),
    ("Finding", "state"),
    ("StatusChange", "at"),
    ("StatusChange", "kep_path"),
    ("StatusChange", "valid_to"),
    ("Decision", "kep_path"),
    ("Decision", "decided_at"),
    ("Section", "kep_path"),
    ("Issue", "number"),
    ("PullRequest", "number"),
    ("PullRequest", "merged_at"),
    ("Comment", "created_at"),
    ("Release", "ordinal"),
    ("Release", "released_at"),
    ("Document", "kind"),
    ("Person", "pagerank"),
    ("Person", "betweenness"),
    ("Person", "wcc_id"),
    ("Person", "lp_community_id"),
)

FULLTEXT: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("KEP", ("title", "summary")),
    ("Section", ("heading", "text")),
    ("Person", ("login", "name")),
    ("FeatureGate", ("name",)),
    ("Issue", ("title",)),
    ("PullRequest", ("title",)),
    ("Comment", ("body",)),
    ("SIG", ("display_name", "mission")),
    ("Decision", ("summary",)),
)

# Secondary labels share the keyspace of their primary label, so a UNIQUE key is safe on them too.
UNIQUE_KEY_LABELS: tuple[str, ...] = tuple(sorted(NODE_LABELS))


# MANDATORY node constraints (03 §13), applied only while every existing node already satisfies them.
MANDATORY_NODE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("KEP", ("key", "source_url", "observed_at")),
    ("KEP", ("status", "owning_sig")),
    ("Finding", ("key", "source_url", "observed_at")),
    ("Finding", ("kind", "kep_path", "state", "rule_version")),
    ("StatusChange", ("key", "source_url", "observed_at")),
    ("StatusChange", ("kind", "field", "at", "valid_to")),
    ("Decision", ("key", "source_url", "observed_at")),
    ("Decision", ("kind", "kep_path", "derived")),
)


@dataclass
class ApplyReport:
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


def _already(exc: Exception) -> bool:
    text = str(exc).lower()
    return "already indexed" in text or "already exists" in text


def _run(pool: FalkorPool, graph: str, query: str, report: ApplyReport, name: str) -> None:
    try:
        pool.run_sync(Role.WRITER, graph, query, read_only=False, timeout_ms=WRITE_TIMEOUT_MS)
        report.created.append(name)
    except ResponseError as exc:
        if _already(exc):
            report.existing.append(name)
        else:
            log.error("schema_apply_failed", item=name, error=str(exc))
            report.failed.append(f"{name}: {exc}")


def _constraint(pool: FalkorPool, graph: str, label: str, report: ApplyReport) -> None:
    name = f"UNIQUE {label}.key"
    conn = pool.client(Role.WRITER).connection
    try:
        conn.execute_command("GRAPH.CONSTRAINT", "CREATE", graph, "UNIQUE", "NODE", label, "PROPERTIES", 1, "key")
        report.created.append(name)
    except ResponseError as exc:
        if _already(exc):
            report.existing.append(name)
        else:
            log.error("schema_apply_failed", item=name, error=str(exc))
            report.failed.append(f"{name}: {exc}")


def _mandatory(pool: FalkorPool, graph: str, label: str, props: tuple[str, ...], report: ApplyReport) -> None:
    name = f"MANDATORY {label}({', '.join(props)})"
    missing = " OR ".join(f"n.{p} IS NULL" for p in props)
    out = pool.run_sync(
        Role.WRITER, graph, f"MATCH (n:{label}) WHERE {missing} RETURN count(n)", read_only=True,
        timeout_ms=WRITE_TIMEOUT_MS,
    )  # fmt: skip
    violating = int(out.rows[0][0]) if out.rows else 0
    if violating:
        log.warning("mandatory_constraint_skipped", item=name, violating_nodes=violating)
        report.skipped.append(f"{name}: {violating} existing nodes lack a property")
        return
    conn = pool.client(Role.WRITER).connection
    try:
        conn.execute_command(
            "GRAPH.CONSTRAINT", "CREATE", graph, "MANDATORY", "NODE", label, "PROPERTIES", len(props), *props
        )
        report.created.append(name)
    except ResponseError as exc:
        if _already(exc):
            report.existing.append(name)
        else:
            log.error("schema_apply_failed", item=name, error=str(exc))
            report.failed.append(f"{name}: {exc}")


def list_indexes(pool: FalkorPool, graph: str) -> list[dict[str, Any]]:
    out = pool.run_sync(Role.WRITER, graph, "CALL db.indexes()", read_only=True, timeout_ms=WRITE_TIMEOUT_MS)
    return [
        {"label": r[0], "properties": list(r[1]), "types": {k: list(v) for k, v in dict(r[2]).items()}, "status": r[7]}
        for r in out.rows
    ]


def list_constraints(pool: FalkorPool, graph: str) -> list[dict[str, Any]]:
    out = pool.run_sync(Role.WRITER, graph, "CALL db.constraints()", read_only=True, timeout_ms=WRITE_TIMEOUT_MS)
    return [{"type": r[0], "label": r[1], "properties": list(r[2]), "status": r[4]} for r in out.rows]


def apply_schema(pool: FalkorPool, graph: str, wait_seconds: float = 60.0) -> ApplyReport:
    report = ApplyReport()
    for label in sorted(NODE_LABELS):
        _run(pool, graph, f"CREATE INDEX FOR (n:{label}) ON (n.key)", report, f"RANGE {label}.key")
    for label, prop in SECONDARY_RANGE:
        _run(pool, graph, f"CREATE INDEX FOR (n:{label}) ON (n.{prop})", report, f"RANGE {label}.{prop}")
    existing_ft = {
        (ix["label"], p) for ix in list_indexes(pool, graph) for p, types in ix["types"].items() if "FULLTEXT" in types
    }
    for label, props in FULLTEXT:
        missing = [p for p in props if (label, p) not in existing_ft]
        name = f"FULLTEXT {label}({', '.join(props)})"
        if not missing:
            report.existing.append(name)
            continue
        args = ", ".join(f"'{p}'" for p in missing)
        _run(pool, graph, f"CALL db.idx.fulltext.createNodeIndex('{label}', {args})", report, name)
    for label in UNIQUE_KEY_LABELS:
        _constraint(pool, graph, label, report)
    for label, props in MANDATORY_NODE:
        _mandatory(pool, graph, label, props, report)

    deadline = time.monotonic() + wait_seconds
    while True:
        pending = [c for c in list_constraints(pool, graph) if c["status"] != "OPERATIONAL"]
        failed = [c for c in pending if c["status"] == "FAILED"]
        for c in failed:
            report.failed.append(f"constraint {c['type']} {c['label']}{c['properties']} FAILED")
        if failed or not pending or time.monotonic() > deadline:
            if pending and not failed:
                report.failed.append(f"{len(pending)} constraints not operational after {wait_seconds}s")
            break
        time.sleep(0.5)
    log.info("schema_applied", graph=graph, created=len(report.created), existing=len(report.existing),
             skipped=len(report.skipped), failed=len(report.failed))  # fmt: skip
    return report
