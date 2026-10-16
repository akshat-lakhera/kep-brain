"""Every test under this directory needs a FalkorDB; mark it `integration` so CI can split the suites."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db.falkordb import GRAPH_KEP, FalkorPool, Role

HERE = Path(__file__).resolve().parent

# The upstream commits the live-graph tests' exact values were recorded against. When the loaded graph was
# synced from other commits the values legitimately differ, so those tests skip instead of failing.
ENHANCEMENTS_PIN = "8659e382efab7340d70de52432ee8f3d9979b797"
COMMUNITY_PIN = "53c338ecba4a2a9240f6654cca1d6a9dac25c785"
_TREE_SHA = re.compile(r"/tree/([0-9a-f]{40})/")


def live_graph_pinned(pool: FalkorPool, extra: str | None = None, minimum: int = 0) -> bool:
    """True when graph `kep` holds data from the pinned commits (and `extra` counts at least `minimum`)."""
    try:
        if GRAPH_KEP not in pool.list_graphs():
            return False
        kep = pool.run_sync(
            Role.READER, GRAPH_KEP, "MATCH (k:KEP) RETURN k.url LIMIT 1", read_only=True, timeout_ms=2000
        )
        sig = pool.run_sync(
            Role.READER,
            GRAPH_KEP,
            "MATCH (d:Document {kind: 'sigs_yaml'}) RETURN d.source_sha LIMIT 1",
            read_only=True,
            timeout_ms=2000,
        )
        found = _TREE_SHA.search(str(kep.rows[0][0])) if kep.rows else None
        if not found or found.group(1) != ENHANCEMENTS_PIN or not sig.rows or sig.rows[0][0] != COMMUNITY_PIN:
            return False
        if extra:
            n = pool.run_sync(Role.READER, GRAPH_KEP, extra, read_only=True, timeout_ms=5000).rows[0][0]
            return bool(n >= minimum)
        return True
    except Exception:  # noqa: BLE001 - an unreachable database means "not loaded"
        return False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.integration)
