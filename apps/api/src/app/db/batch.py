"""Idempotent batch writer for the worker (03 §3.3, ADR 0008).

Labels and relationship types are interpolated into Cypher only after an
allow-list check against `app.schema.labels`; every value travels as a
query parameter.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import structlog

from app.db.falkordb import WRITE_TIMEOUT_MS, FalkorPool, Role
from app.ingest.common import iso
from app.schema.apply import MANDATORY_NODE
from app.schema.labels import NODE_LABELS, REL_TYPES, VALID_TO_OPEN

log = structlog.get_logger(__name__)
BATCH_SIZE = 500


def content_hash(props: dict[str, Any]) -> str:
    canonical = json.dumps(props, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _chunks(rows: Sequence[dict[str, Any]], size: int = BATCH_SIZE) -> Iterable[Sequence[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _mandatory_props(label: str) -> tuple[str, ...]:
    """Properties a MANDATORY constraint requires on `label` nodes at the moment they are created."""
    seen: dict[str, None] = {}
    for lab, props in MANDATORY_NODE:
        if lab == label:
            seen.update(dict.fromkeys(props))
    return tuple(seen)


def _clean(props: dict[str, Any]) -> dict[str, Any]:
    """Drop None values: FalkorDB cannot store null, and absent means unknown (P5)."""
    return {k: v for k, v in props.items() if v is not None}


class BatchWriter:
    def __init__(self, pool: FalkorPool, graph: str, sync_run_id: str) -> None:
        self.pool = pool
        self.graph = graph
        self.sync_run_id = sync_run_id
        self.observed_at = int(time.time())

    def _run(self, query: str, params: dict[str, Any]) -> dict[str, int]:
        out = self.pool.run_sync(Role.WRITER, self.graph, query, params, read_only=False, timeout_ms=WRITE_TIMEOUT_MS)
        return out.stats

    def query(self, query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        """Escape hatch for fixed worker templates (derivations, closures)."""
        out = self.pool.run_sync(
            Role.WRITER, self.graph, query, params or {}, read_only=False, timeout_ms=WRITE_TIMEOUT_MS
        )
        return out.rows

    def upsert_nodes(self, label: str, rows: Sequence[dict[str, Any]], extra_labels: Sequence[str] = ()) -> int:
        """MERGE on `key`; properties are rewritten only when `content_hash` changed."""
        if label not in NODE_LABELS or any(x not in NODE_LABELS for x in extra_labels):
            raise ValueError(f"label not in allow-list: {label} {list(extra_labels)}")
        prepared = []
        for row in rows:
            props = _clean(dict(row))
            if "key" not in props:
                raise ValueError(f"{label} row without key")
            props["content_hash"] = content_hash(props)
            props["observed_at"] = self.observed_at
            props["sync_run_id"] = self.sync_run_id
            prepared.append(props)
        set_labels = "".join(f":{x}" for x in extra_labels)
        written = 0
        mandatory = _mandatory_props(label)
        if mandatory:
            # FalkorDB checks MANDATORY constraints when a node is created, before any SET runs, so
            # MERGE ... ON CREATE SET cannot create such a node: CREATE it with the required properties.
            pattern = ", ".join(["key: r.key", *(f"{p}: r.{p}" for p in mandatory if p != "key")])
            create = (
                f"UNWIND $rows AS r OPTIONAL MATCH (m:{label} {{key: r.key}}) WITH r, m WHERE m IS NULL "
                f"CREATE (n:{label} {{{pattern}}}) SET n += r, n.first_seen_at = r.observed_at"
                + (f" SET n{set_labels}" if set_labels else "")
            )
            update = (
                f"UNWIND $rows AS r MATCH (n:{label} {{key: r.key}}) WHERE n.content_hash <> r.content_hash "
                f"SET n += r" + (f" SET n{set_labels}" if set_labels else "")
            )
            for chunk in _chunks(list({p["key"]: p for p in prepared}.values())):
                written += self._run(create, {"rows": list(chunk)}).get("nodes_created", 0)
                self._run(update, {"rows": list(chunk)})
        else:
            query = (
                f"UNWIND $rows AS r MERGE (n:{label} {{key: r.key}}) "
                f"ON CREATE SET n += r, n.first_seen_at = r.observed_at "
                f"WITH n, r WHERE n.content_hash <> r.content_hash OR n.first_seen_at = r.observed_at "
                f"SET n += r" + (f" SET n{set_labels}" if set_labels else "")
            )
            for chunk in _chunks(prepared):
                written += self._run(query, {"rows": list(chunk)}).get("nodes_created", 0)
        log.info("upsert_nodes", label=label, rows=len(prepared), created=written)
        return written

    def upsert_edges(
        self,
        rel: str,
        from_label: str,
        to_label: str,
        rows: Sequence[dict[str, Any]],
        identity: Sequence[str] = (),
    ) -> int:
        """MERGE edges between existing nodes. Each row: {from, to, props: {...}}.

        `identity` names properties that distinguish parallel edges of the same
        type (e.g. `stage` on PRR_APPROVED); they go into the MERGE pattern.
        """
        if rel not in REL_TYPES or from_label not in NODE_LABELS or to_label not in NODE_LABELS:
            raise ValueError(f"edge not in allow-list: ({from_label})-[{rel}]->({to_label})")
        prepared = []
        for row in rows:
            props = _clean(dict(row.get("props", {})))
            props["observed_at"] = self.observed_at
            props["sync_run_id"] = self.sync_run_id
            for ident in identity:
                if ident not in props:
                    raise ValueError(f"{rel} edge missing identity property {ident}")
            prepared.append({"from": row["from"], "to": row["to"], "props": props})
        ident_pattern = ", ".join(f"{p}: r.props.{p}" for p in identity)
        pattern = f"[e:{rel} {{{ident_pattern}}}]" if ident_pattern else f"[e:{rel}]"
        query = (
            f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.from}}) MATCH (b:{to_label} {{key: r.to}}) "
            f"MERGE (a)-{pattern}->(b) SET e += r.props"
        )
        created = 0
        for chunk in _chunks(prepared):
            stats = self._run(query, {"rows": list(chunk)})
            created += stats.get("relationships_created", 0)
        log.info("upsert_edges", rel=rel, rows=len(prepared), created=created)
        return created

    def merge_open_edges(self, rel: str, from_label: str, to_label: str, rows: Sequence[dict[str, Any]]) -> None:
        """One open interval per (from, rel, to): created once with its envelope, then only re-observed (03 §3.3).

        `rows` are `{from, to, props}`; None-valued props are dropped so a MERGE never writes nulls.
        """
        self._check_edge(rel, from_label, to_label)
        prepared = [
            {
                "from": r["from"],
                "to": r["to"],
                "props": {k: v for k, v in (r.get("props") or {}).items() if v is not None},
            }
            for r in rows
        ]
        query = (
            f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.from}}) MATCH (b:{to_label} {{key: r.to}}) "
            f"MERGE (a)-[e:{rel} {{valid_to: $open}}]->(b) "
            "ON CREATE SET e += r.props, e.observed_at = $now, e.sync_run_id = $run "
            "ON MATCH SET e.observed_at = $now, e.sync_run_id = $run"
        )
        for chunk in _chunks(prepared):
            self._run(
                query, {"rows": list(chunk), "open": VALID_TO_OPEN, "now": self.observed_at, "run": self.sync_run_id}
            )

    def close_absent_edges(
        self,
        rel: str,
        from_label: str,
        to_label: str | None,
        current: Mapping[str, Sequence[str]],
        at: int | None = None,
        *,
        keyed_by_target: bool = False,
    ) -> None:
        """Close open `rel` edges that this sync no longer sees (03 §3.3).

        `current` maps a subject key to the keys still connected to it. By default the subject is the edge's
        source and the listed keys are targets; with `keyed_by_target` the subject is the target and the listed
        keys are sources (leadership edges are keyed by the group). `to_label` None matches any target label.
        """
        self._check_edge(rel, from_label, *(() if to_label is None else (to_label,)))
        when = self.observed_at if at is None else at
        target = f"b:{to_label}" if to_label else "b"
        if keyed_by_target:
            match = (
                f"MATCH (a:{from_label})-[e:{rel}]->({target} {{key: r.key}}) "
                "WHERE e.valid_to = $open AND NOT a.key IN r.current"
            )
        else:
            match = (
                f"MATCH (a:{from_label} {{key: r.key}})-[e:{rel}]->({target}) "
                "WHERE e.valid_to = $open AND NOT b.key IN r.current"
            )
        rows = [{"key": k, "current": list(v)} for k, v in current.items()]
        for chunk in _chunks(rows):
            self._run(
                f"UNWIND $rows AS r {match} SET e.valid_to = $at, e.valid_to_iso = $at_iso",
                {"rows": list(chunk), "open": VALID_TO_OPEN, "at": when, "at_iso": iso(when)},
            )

    @staticmethod
    def _check_edge(rel: str, *labels: str) -> None:
        if rel not in REL_TYPES or any(label not in NODE_LABELS for label in labels):
            raise ValueError("edge not in allow-list")
