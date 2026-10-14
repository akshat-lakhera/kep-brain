"""Schema apply is idempotent on a throwaway graph (03 §12, §13)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.db.falkordb import FalkorPool, Role
from app.schema.apply import FULLTEXT, SECONDARY_RANGE, apply_schema, list_constraints, list_indexes
from app.schema.labels import NODE_LABELS
from app.settings import Settings

GRAPH = "test_schema_apply"


@pytest.fixture
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings())
    try:
        p.list_graphs()
    except Exception as exc:  # noqa: BLE001 - no dev FalkorDB: skip, do not fail
        pytest.skip(f"FalkorDB not reachable: {exc}")
    yield p
    if GRAPH in p.list_graphs():
        p.graph(Role.WRITER, GRAPH).delete()
    p.close()


def test_apply_twice_is_idempotent(pool: FalkorPool) -> None:
    first = apply_schema(pool, GRAPH)
    assert first.ok, first.failed
    assert first.created
    second = apply_schema(pool, GRAPH)
    assert second.ok, second.failed
    assert second.created == []
    assert len(second.existing) == len(first.created) + len(first.existing)

    indexes = {ix["label"]: ix["types"] for ix in list_indexes(pool, GRAPH)}
    for label in NODE_LABELS:
        assert "RANGE" in indexes[label]["key"]
    for label, prop in SECONDARY_RANGE:
        assert "RANGE" in indexes[label][prop]
    for label, props in FULLTEXT:
        for prop in props:
            assert "FULLTEXT" in indexes[label][prop]
    constraints = list_constraints(pool, GRAPH)
    assert {c["label"] for c in constraints if c["type"] == "UNIQUE"} == set(NODE_LABELS)
    assert all(c["status"] == "OPERATIONAL" for c in constraints)


KEP_NODE = "CREATE (:KEP {key: 'k', source_url: 'u', observed_at: 1, status: 'provisional', owning_sig: 'sig-node'})"


def test_unique_key_is_enforced(pool: FalkorPool) -> None:
    assert apply_schema(pool, GRAPH).ok
    pool.run_sync(Role.WRITER, GRAPH, KEP_NODE, read_only=False, timeout_ms=5000)
    with pytest.raises(Exception, match="(?i)unique|constraint"):
        pool.run_sync(Role.WRITER, GRAPH, KEP_NODE, read_only=False, timeout_ms=5000)
