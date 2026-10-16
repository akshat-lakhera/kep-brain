"""FalkorDB access by role (02 §4.2–§4.5, ADR 0005, ADR 0022).

Four roles map to four ACL users in `aclfile` mode; in `single` mode
(C1 fallback 7) every role uses the default user. Reads on the request
path always go through `GRAPH.RO_QUERY`.

falkordb-py 1.7.1 is synchronous and probes `INFO server` in its
constructor, so clients are built lazily and every call runs in a worker
thread to keep the event loop free.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import anyio
import structlog
from falkordb import FalkorDB, Graph
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.errors import AppError
from app.settings import Settings

log = structlog.get_logger(__name__)

GRAPH_KEP = "kep"
GRAPH_OPS = "ops"
READ_TIMEOUT_MS = 2000
WRITE_TIMEOUT_MS = 30000
MAX_ROWS = 200


class Role(StrEnum):
    READER = "kb_reader"
    MEMORY = "kb_memory"
    OPS = "kb_ops"
    WRITER = "kb_writer"


@dataclass(frozen=True)
class QueryOutput:
    header: list[str]
    rows: list[list[Any]]
    run_time_ms: float
    stats: dict[str, int]

    def as_dicts(self) -> list[dict[str, Any]]:
        """Rows as header-keyed dicts."""
        return [dict(zip(self.header, row, strict=False)) for row in self.rows]


def _is_timeout(exc: Exception) -> bool:
    text = str(exc).lower()
    return "timeout" in text or "timed out" in text


class FalkorPool:
    """One lazily built client per role, shared across threads."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: dict[Role, FalkorDB] = {}
        self._lock = threading.Lock()

    def _credentials(self, role: Role) -> tuple[str | None, str | None]:
        s = self._settings
        if s.falkordb_acl_mode == "single":
            pw = s.falkordb_password.get_secret_value() if s.falkordb_password else None
            return None, pw
        secret = {
            Role.READER: s.falkordb_reader_password,
            Role.MEMORY: s.falkordb_memory_password,
            Role.OPS: s.falkordb_ops_password,
            Role.WRITER: s.falkordb_writer_password,
        }[role]
        if secret is None:
            raise AppError("graph_unavailable", {"reason": f"no password configured for {role.value}"})
        return role.value, secret.get_secret_value()

    def client(self, role: Role) -> FalkorDB:
        with self._lock:
            existing = self._clients.get(role)
            if existing is not None:
                return existing
            username, password = self._credentials(role)
            client = FalkorDB(
                host=self._settings.falkordb_host,
                port=self._settings.falkordb_port,
                username=username,
                password=password,
                socket_timeout=self._settings.falkordb_timeout_seconds + WRITE_TIMEOUT_MS / 1000,
                socket_connect_timeout=self._settings.falkordb_timeout_seconds,
                health_check_interval=30,
                client_name=f"kep-brain:{role.value}",
            )
            self._clients[role] = client
            return client

    def graph(self, role: Role, name: str) -> Graph:
        return self.client(role).select_graph(name)

    # -- synchronous primitives (worker and threads) -------------------------

    def run_sync(
        self,
        role: Role,
        graph: str,
        query: str,
        params: dict[str, Any] | None = None,
        *,
        read_only: bool,
        timeout_ms: int,
    ) -> QueryOutput:
        try:
            # The client connects in its constructor, so a dead or slow database fails here, not in the query.
            g = self.graph(role, graph)
        except (RedisConnectionError, ConnectionRefusedError, OSError, RedisTimeoutError) as exc:
            log.warning("falkordb_unavailable", error=str(exc))
            raise AppError("graph_unavailable") from exc
        try:
            if read_only:
                res = g.ro_query(query, params, timeout=timeout_ms)
            else:
                res = g.query(query, params, timeout=timeout_ms)
        except (RedisConnectionError, ConnectionRefusedError, OSError) as exc:
            log.warning("falkordb_unavailable", error=str(exc))
            raise AppError("graph_unavailable") from exc
        except RedisTimeoutError as exc:
            raise AppError("graph_timeout") from exc
        except ResponseError as exc:
            if _is_timeout(exc):
                raise AppError("graph_timeout") from exc
            raise
        header = [h[1] if isinstance(h, list | tuple) else str(h) for h in (res.header or [])]
        stats = {
            "nodes_created": res.nodes_created,
            "relationships_created": res.relationships_created,
            "properties_set": res.properties_set,
            "nodes_deleted": res.nodes_deleted,
        }
        return QueryOutput(header=header, rows=res.result_set or [], run_time_ms=res.run_time_ms, stats=stats)

    def list_graphs(self) -> list[str]:
        try:
            return list(self.client(Role.READER).list_graphs())
        except (RedisConnectionError, ConnectionRefusedError, OSError, RedisTimeoutError) as exc:
            raise AppError("graph_unavailable") from exc

    # -- async wrappers (api) -------------------------------------------------

    async def ro_query(
        self, graph: str, query: str, params: dict[str, Any] | None = None, timeout_ms: int = READ_TIMEOUT_MS
    ) -> QueryOutput:
        return await anyio.to_thread.run_sync(
            lambda: self.run_sync(Role.READER, graph, query, params, read_only=True, timeout_ms=timeout_ms)
        )

    async def write(
        self, role: Role, graph: str, query: str, params: dict[str, Any] | None = None, timeout_ms: int = 5000
    ) -> QueryOutput:
        if role is Role.READER:
            raise ValueError("the reader role cannot write")
        return await anyio.to_thread.run_sync(
            lambda: self.run_sync(role, graph, query, params, read_only=False, timeout_ms=timeout_ms)
        )

    async def ping(self) -> list[str]:
        return await anyio.to_thread.run_sync(self.list_graphs)

    def close(self) -> None:
        with self._lock:
            for client in self._clients.values():
                with contextlib.suppress(Exception):  # best effort on shutdown
                    client.connection.close()
            self._clients.clear()
