"""Answer cache in the `ops` graph: validated answers keyed by question and graph version."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

import structlog

from app.db.falkordb import GRAPH_KEP, GRAPH_OPS, FalkorPool, Role

log = structlog.get_logger(__name__)

# Observed-at stamps are rewritten only when a node's content hash changes, so these maxima move only when
# the corpus does (a re-sync that finds nothing new leaves them alone).
GRAPH_VERSION = (
    "OPTIONAL MATCH (k:KEP) WITH max(k.observed_at) AS kep "
    "OPTIONAL MATCH (i:Issue) WITH kep, max(i.observed_at) AS issue "
    "OPTIONAL MATCH (f:Finding) RETURN kep, issue, max(f.observed_at)"
)  # OPTIONAL so a graph without findings (or issues) still yields one row and the version keeps moving
LOOKUP = "MATCH (c:AnswerCache {key: $key}) RETURN c.response_json, c.created_at"
STORE = (
    "MERGE (c:AnswerCache {key: $key}) "
    "SET c.question = $question, c.response_json = $response, c.created_at = $now, c.model = $model"
)
CLEAR = "MATCH (c:AnswerCache) DELETE c"
_PUNCT = re.compile(r"[\s?!.]+$")


def normalise(question: str) -> str:
    return _PUNCT.sub("", " ".join(question.lower().split()))


def cache_key(question: str, version: str) -> str:
    return hashlib.sha256(f"{normalise(question)}\n{version}".encode()).hexdigest()


class AnswerCache:
    def __init__(self, pool: FalkorPool) -> None:
        self.pool = pool

    async def version(self) -> str:
        out = await self.pool.ro_query(GRAPH_KEP, GRAPH_VERSION)
        return ":".join(str(v) for v in out.rows[0]) if out.rows else "empty"

    async def get(self, question: str) -> dict[str, Any] | None:
        try:
            key = cache_key(question, await self.version())
            out = await self.pool.write(Role.OPS, GRAPH_OPS, LOOKUP, {"key": key})
        except Exception as exc:  # noqa: BLE001 - the cache is best effort; a miss falls through to the agent
            log.warning("answer_cache_unavailable", error=str(exc)[:200])
            return None
        if not out.rows:
            return None
        response: dict[str, Any] = json.loads(out.rows[0][0])
        response["cached"] = True
        response["cached_at"] = int(out.rows[0][1])
        return response

    async def put(self, question: str, response: dict[str, Any]) -> None:
        try:
            key = cache_key(question, await self.version())
            await self.pool.write(Role.OPS, GRAPH_OPS, STORE, {
                "key": key, "question": question, "now": int(time.time()), "model": response.get("model", ""),
                "response": json.dumps(response, ensure_ascii=False, default=str, separators=(",", ":")),
            })  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - failing to cache must not fail the answer
            log.warning("answer_cache_store_failed", error=str(exc)[:200])

    async def clear(self) -> int:
        out = await self.pool.write(Role.OPS, GRAPH_OPS, CLEAR)
        return out.stats.get("nodes_deleted", 0)
