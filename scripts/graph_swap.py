"""Blue-green swap of the `kep` graph with GRAPH.COPY.

The worker can load a fresh graph next to the live one (`python -m app.worker all --graph kep_fresh`). This
script then puts it behind the API without a rebuild:

1. `GRAPH.COPY kep kep_old`   keep the graph the API serves now as a backup (an older `kep_old` is dropped);
2. `GRAPH.DELETE kep`         GRAPH.COPY refuses an existing destination, so the live key is removed first
                              (reads during the gap answer empty, see `app.db.falkordb`);
3. `GRAPH.COPY kep_fresh kep` the fresh graph becomes the live one; `kep_fresh` is kept unless `--drop-fresh`;
4. `MATCH (c:AnswerCache) DELETE c` in the `ops` graph, because cached answers are keyed by graph version.

Connection settings are the API's: FALKORDB_HOST, FALKORDB_PORT, FALKORDB_PASSWORD, and in `aclfile` mode
FALKORDB_ACL_MODE=aclfile with FALKORDB_WRITER_PASSWORD (user `kb_writer`). A repo-root `.env` is read when
present; the environment wins. Run it with the API's virtual environment, which has the `falkordb` client:

    cd apps/api && uv run python ../../scripts/graph_swap.py --dry-run
    cd apps/api && uv run python ../../scripts/graph_swap.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from falkordb import FalkorDB

LIVE, FRESH, OLD, OPS = "kep", "kep_fresh", "kep_old", "ops"
CLEAR_CACHE = "MATCH (c:AnswerCache) DELETE c"


def load_dotenv(path: Path) -> None:
    """Minimal KEY=VALUE reader for the repo-root .env; existing environment variables are kept."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip("'\"")
        if key.strip() and value and key.strip() not in os.environ:
            os.environ[key.strip()] = value


def connect() -> FalkorDB:
    username: str | None = None
    password = os.environ.get("FALKORDB_PASSWORD") or None
    if os.environ.get("FALKORDB_ACL_MODE", "single") == "aclfile":
        username, password = "kb_writer", os.environ.get("FALKORDB_WRITER_PASSWORD") or None
        if password is None:
            sys.exit("FALKORDB_WRITER_PASSWORD is required in aclfile mode")
    return FalkorDB(
        host=os.environ.get("FALKORDB_HOST", "localhost"),
        port=int(os.environ.get("FALKORDB_PORT", "6380")),
        username=username,
        password=password,
        socket_timeout=120,
        socket_connect_timeout=5,
    )


def swap(db: FalkorDB, *, drop_fresh: bool, dry_run: bool) -> int:
    graphs = set(db.list_graphs())
    if FRESH not in graphs:
        print(f"no graph named {FRESH}: load one first (python -m app.worker all --graph {FRESH})")
        return 1
    plan: list[tuple[str, str]] = []
    if OLD in graphs:
        plan.append((f"GRAPH.DELETE {OLD}", OLD))
    if LIVE in graphs:
        plan.append((f"GRAPH.COPY {LIVE} {OLD}", LIVE))
        plan.append((f"GRAPH.DELETE {LIVE}", LIVE))
    plan.append((f"GRAPH.COPY {FRESH} {LIVE}", FRESH))
    if drop_fresh:
        plan.append((f"GRAPH.DELETE {FRESH}", FRESH))
    plan.append((f"GRAPH.QUERY {OPS} {CLEAR_CACHE}", OPS))
    for step, _ in plan:
        print(("would run: " if dry_run else "running:   ") + step)
    if dry_run:
        return 0
    if OLD in graphs:
        db.select_graph(OLD).delete()
    if LIVE in graphs:
        db.select_graph(LIVE).copy(OLD)
        db.select_graph(LIVE).delete()
    db.select_graph(FRESH).copy(LIVE)
    if drop_fresh:
        db.select_graph(FRESH).delete()
    if OPS in graphs:
        deleted = db.select_graph(OPS).query(CLEAR_CACHE).nodes_deleted
        print(f"answer cache cleared: {deleted} entries")
    live_nodes = db.select_graph(LIVE).ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
    print(f"{LIVE} now has {live_nodes} nodes; previous graph kept as {OLD}" if LIVE in graphs else
          f"{LIVE} now has {live_nodes} nodes")  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Swap {FRESH} in as {LIVE}, keeping the previous graph as {OLD}.")
    parser.add_argument("--drop-fresh", action="store_true", help=f"delete {FRESH} after the copy")
    parser.add_argument("--dry-run", action="store_true", help="print the steps without running them")
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return swap(connect(), drop_fresh=args.drop_fresh, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
