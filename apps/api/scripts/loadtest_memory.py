"""Concurrent load test for the per-user memory routes. Never calls /v1/ask (no LLM).

Each simulated user owns a fresh ULID memory id. A round is: one write-equivalent (DELETE of one fact, which
checks the graph and runs a write query) and recall-equivalent reads (GET /v1/memory/me, GET /v1/agents/board).
Users are seeded once with a direct store.remember call so the graph holds real episodes, facts and playbooks.

Usage: uv run python scripts/loadtest_memory.py [--users 50] [--rounds 10] [--concurrency 25]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from ulid import ULID

from app.db.falkordb import FalkorPool
from app.memory import store
from app.settings import Settings

API = os.environ.get("KEP_API", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[3]


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 1) if ordered else 0.0


async def seed(pool: FalkorPool, memory_id: str, n: int) -> None:
    for i in range(n):
        await store.remember(
            pool,
            memory_id,
            {
                "request_id": f"lt-{memory_id}-{i}",
                "question": f"Who approves KEP-{4000 + i} in sig-node?",
                "answer_markdown": "seeded",
                "abstained": False,
                "citations": [{"label": "KEP", "key": f"keps/sig-node/{4000 + i}-x", "title": "t", "url": "https://x"}],
                "tool_calls": [{"name": "find_entities"}, {"name": "who_owns"}],
            },
        )


async def user(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    memory_id: str,
    rounds: int,
    lat: dict[str, list[float]],
    errs: dict[str, int],
) -> None:
    headers = {"X-Kep-Memory-Id": memory_id}

    async def call(name: str, method: str, path: str) -> None:
        async with sem:
            t0 = time.perf_counter()
            try:
                r = await client.request(method, path, headers=headers)
                ok = r.status_code < 400 or (name == "write_fact" and r.status_code == 404)
            except httpx.HTTPError:
                ok = False
            lat[name].append((time.perf_counter() - t0) * 1000)
            if not ok:
                errs[name] += 1

    for _ in range(rounds):
        await call("write_fact", "DELETE", "/v1/memory/me/facts/context:release:v0.00")
        await call("recall_me", "GET", "/v1/memory/me")
        await call("board", "GET", "/v1/agents/board")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=25)
    ap.add_argument("--seed", type=int, default=2, help="episodes seeded per user")
    args = ap.parse_args()

    pool = FalkorPool(Settings(_env_file=ROOT / ".env"))  # type: ignore[call-arg]
    ids = [str(ULID()) for _ in range(args.users)]
    lat: dict[str, list[float]] = defaultdict(list)
    errs: dict[str, int] = defaultdict(int)
    started = time.perf_counter()
    try:
        sem = asyncio.Semaphore(4)

        async def seeded(i: str) -> None:
            async with sem:
                await seed(pool, i, args.seed)

        await asyncio.gather(*(seeded(i) for i in ids))
        seed_s = time.perf_counter() - started
        limit = asyncio.Semaphore(args.concurrency)
        t0 = time.perf_counter()
        async with httpx.AsyncClient(base_url=API, timeout=30) as client:
            await asyncio.gather(*(user(client, limit, i, args.rounds, lat, errs) for i in ids))
        wall = time.perf_counter() - t0
    finally:
        async with httpx.AsyncClient(base_url=API, timeout=30) as client:
            for i in ids:
                await client.delete("/v1/memory/me", headers={"X-Kep-Memory-Id": i})
        pool.close()

    endpoints: dict[str, Any] = {}
    for name, values in lat.items():
        endpoints[name] = {
            "count": len(values),
            "errors": errs[name],
            "p50_ms": pct(values, 0.50),
            "p95_ms": pct(values, 0.95),
            "p99_ms": pct(values, 0.99),
            "mean_ms": round(statistics.fmean(values), 1),
        }
        print(
            f"{name:12} n={len(values):5} err={errs[name]:3} p50={pct(values, 0.5):8.1f} "
            f"p95={pct(values, 0.95):8.1f} p99={pct(values, 0.99):8.1f} ms"
        )
    total = sum(len(v) for v in lat.values())
    report = {
        "api": API,
        "users": args.users,
        "rounds": args.rounds,
        "concurrency": args.concurrency,
        "requests": total,
        "wall_s": round(wall, 2),
        "rps": round(total / wall, 1),
        "seed_s": round(seed_s, 2),
        "endpoints": endpoints,
    }
    print(f"{total} requests in {wall:.1f}s = {total / wall:.1f} rps")
    out = ROOT / "evals" / "loadtest"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2))
    print(path)


if __name__ == "__main__":
    asyncio.run(main())
