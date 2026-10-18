"""Worker CLI: `python -m app.worker <command>`.

Commands: schema-apply, sync-docs, sync-history, sync-owners, sync-tickets, derive, all, stats, schedule.
Every run gets a ULID `sync_run_id` stamped on the nodes and edges it writes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from typing import Any

import structlog
from ulid import ULID

from app.db.batch import BatchWriter
from app.db.falkordb import GRAPH_KEP, WRITE_TIMEOUT_MS, FalkorPool, Role
from app.ingest.common import COMMUNITY_REPO
from app.ingest.derive import derive_decisions, write_pagerank
from app.ingest.docs import Corpus, build_corpus, sync_docs
from app.ingest.findings import detect_findings
from app.ingest.history import sync_history
from app.ingest.owners import sync_owners
from app.ingest.repos import ensure_repo
from app.ingest.sigs import SIGS_PATH
from app.ingest.tickets import sync_tickets
from app.logging import configure_logging
from app.schema.apply import apply_schema
from app.settings import Settings, get_settings
from app.worker.runs import RunRecorder, heartbeat

log = structlog.get_logger(__name__)

# Bump when the doc or history mapping changes, so an unchanged upstream is re-read once with the new code.
INGEST_VERSION = "4"  # 4: the product document (app/data/kep_brain.md) joins sync-docs
SYNC_MARKER_NODE = f"{COMMUNITY_REPO}:{SIGS_PATH}"  # the sigs.yaml Document carries the per-step sync markers


class Worker:
    def __init__(self, settings: Settings, graph: str, force: bool = False) -> None:
        self.settings = settings
        self.graph = graph
        self.force = force
        self._shas: tuple[str, str] | None = None
        self.pool = FalkorPool(settings)
        self.run_id = str(ULID())
        self._corpus: Corpus | None = None
        self._community_sha: str | None = None

    def close(self) -> None:
        self.pool.close()
        if self._corpus is not None:
            self._corpus.git.close()
            self._corpus.community_git.close()
            self._corpus = None

    def writer(self) -> BatchWriter:
        return BatchWriter(self.pool, self.graph, self.run_id)

    def source_shas(self) -> tuple[str, str]:
        """(enhancements, community) commits this run reads; the repositories are cloned or fetched once."""
        if self._shas is None:
            self._shas = (ensure_repo(self.settings, "enhancements"), ensure_repo(self.settings, "community"))
            self._community_sha = self._shas[1]
        return self._shas

    def corpus(self) -> Corpus:
        if self._corpus is None:
            self._corpus = build_corpus(self.settings, self.source_shas())
        return self._corpus

    def _marker(self) -> str:
        enhancements, community = self.source_shas()
        return f"{INGEST_VERSION}:{enhancements}:{community}"

    def _is_synced(self, prop: str) -> bool:
        """True when `prop` on the sigs Document records a finished sync of exactly these commits."""
        if self.force:
            return False
        rows = self.writer().query(f"MATCH (d:Document {{key: $k}}) RETURN d.{prop}", {"k": SYNC_MARKER_NODE})
        return bool(rows) and rows[0][0] == self._marker()

    def _mark_synced(self, prop: str) -> None:
        query = f"MATCH (d:Document {{key: $k}}) SET d.{prop} = $m"
        self.writer().query(query, {"k": SYNC_MARKER_NODE, "m": self._marker()})

    def schema_apply(self) -> dict[str, Any]:
        report = apply_schema(self.pool, self.graph)
        if not report.ok:
            raise RuntimeError("schema apply failed: " + "; ".join(report.failed))
        return {"created": len(report.created), "existing": len(report.existing)}

    def sync_docs(self) -> dict[str, Any]:
        if self._is_synced("docs_synced"):
            log.info("sync_docs_unchanged", marker=self._marker())
            return {"skipped": "unchanged"}
        out = sync_docs(self.writer(), self.corpus(), self.settings)
        self._mark_synced("docs_synced")
        return out

    def sync_history(self) -> dict[str, Any]:
        if self._is_synced("history_synced"):
            log.info("sync_history_unchanged", marker=self._marker())
            return {"skipped": "unchanged"}
        out = sync_history(self.writer(), self.corpus())
        self._mark_synced("history_synced")
        return out

    def community_sha(self) -> str:
        """One community commit per worker run: the doc sync's when it ran, else resolved once here."""
        if self._corpus is not None:
            return self._corpus.community_sha
        if self._community_sha is None:
            self._community_sha = ensure_repo(self.settings, "community")
        return self._community_sha

    def sync_owners(self) -> dict[str, Any]:
        return sync_owners(self.writer(), self.settings, community_sha=self.community_sha())

    def sync_tickets(self) -> dict[str, Any]:
        result: dict[str, Any] = sync_tickets(self.pool, self.settings, graph=self.graph)
        return result

    def derive(self) -> dict[str, Any]:
        return {
            "derive_decisions": derive_decisions(self.writer()),
            "detect_findings": detect_findings(self.writer()),
            "pagerank_people": write_pagerank(self.writer()),
        }

    def stats(self) -> dict[str, Any]:
        def q(query: str) -> list[list[Any]]:
            return self.pool.run_sync(Role.READER, self.graph, query, read_only=True, timeout_ms=WRITE_TIMEOUT_MS).rows

        labels = {r[0]: r[1] for r in q("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) ORDER BY l")}
        rels = {r[0]: r[1] for r in q("MATCH ()-[e]->() RETURN type(e), count(*) ORDER BY type(e)")}
        return {"labels": labels, "relationships": rels}

    def all(self, recorder: RunRecorder | None = None) -> dict[str, Any]:
        steps: list[tuple[str, Callable[[], dict[str, Any]]]] = [
            ("schema-apply", self.schema_apply),
            ("sync-docs", self.sync_docs),
            ("sync-history", self.sync_history),
            ("sync-owners", self.sync_owners),
            ("sync-tickets", self.sync_tickets),
            ("derive", self.derive),
            ("stats", self.stats),
        ]
        return {name: recorder.step(name, fn) if recorder else fn() for name, fn in steps}

    def recorded_all(self) -> dict[str, Any]:
        """`all`, recorded as a SyncRun in the ops graph; a failed run is recorded and re-raised."""
        recorder = RunRecorder(self.pool, self.run_id, "all", self.graph)
        recorder.start()
        try:
            result = self.all(recorder)
        except Exception as exc:
            recorder.finish(ok=False, error=f"{type(exc).__name__}: {exc}")
            raise
        recorder.finish(ok=True)
        return result


COMMANDS = (
    "schema-apply", "sync-docs", "sync-history", "sync-owners", "sync-tickets", "derive", "all", "stats", "schedule",
    "freshness", "coordinate",
)  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.worker", description="KEP Brain ingest worker")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--graph", default=GRAPH_KEP, help="target graph (default: kep)")
    parser.add_argument("--force", action="store_true", help="re-read sources even when their commits are unchanged")
    parser.add_argument("--interval-minutes", type=int, default=15, help="schedule: minutes between full runs")
    parser.add_argument("--limit", type=int, default=None, help="freshness: maximum findings to triage")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings)

    if args.command == "freshness":
        from app.worker.freshness import run_freshness_once

        print(json.dumps(run_freshness_once(settings, limit=args.limit), indent=2, default=str))
        return 0
    if args.command == "coordinate":
        from app.worker.coordinate import run_coordination_tick

        print(json.dumps(run_coordination_tick(settings), indent=2, default=str))
        return 0

    if args.command == "schedule":
        interval_s = args.interval_minutes * 60
        while True:
            worker = Worker(settings, args.graph, args.force)
            try:
                heartbeat(worker.pool, None)
                worker.recorded_all()
            except Exception:  # noqa: BLE001 - keep the scheduler alive; the failure is logged and recorded
                log.exception("scheduled_run_failed", sync_run_id=worker.run_id)
            try:
                heartbeat(worker.pool, int(time.time()) + interval_s)
            except Exception:  # noqa: BLE001 - a missed heartbeat must not stop the scheduler
                log.exception("heartbeat_failed", sync_run_id=worker.run_id)
            finally:
                worker.close()
            time.sleep(interval_s)

    worker = Worker(settings, args.graph, args.force)
    started = time.monotonic()
    log.info("worker_start", command=args.command, graph=args.graph, sync_run_id=worker.run_id)
    try:
        name = "recorded_all" if args.command == "all" else args.command.replace("-", "_")
        handler: Callable[[], dict[str, Any]] = getattr(worker, name)
        result = handler()
    finally:
        worker.close()
    log.info(
        "worker_done", command=args.command, sync_run_id=worker.run_id, seconds=round(time.monotonic() - started, 1)
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
