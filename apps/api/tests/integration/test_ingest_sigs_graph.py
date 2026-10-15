"""sync_sigs loads Subproject nodes and leads idempotently into a throwaway graph."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.db.batch import BatchWriter
from app.db.falkordb import FalkorPool, Role
from app.ingest.sigs import sync_sigs
from app.settings import Settings

GRAPH = "test_sigs_subprojects"
SHA = "b" * 40
V1 = """
sigs:
  - dir: sig-apps
    name: Apps
    subprojects:
      - name: kubectl
        owners: [https://raw.githubusercontent.com/kubernetes/kubectl/master/OWNERS]
        leads: [{github: janetkuo}, {github: Bob}]
      - name: helm
"""
V2 = V1.replace(", {github: Bob}", "")


class FakeGit:
    def __init__(self, text: str) -> None:
        self.text = text

    def read(self, sha: str, path: str) -> str:
        return self.text


@pytest.fixture
def pool() -> Iterator[FalkorPool]:
    p = FalkorPool(Settings())
    try:
        p.list_graphs()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"FalkorDB not reachable: {exc}")
    yield p
    if GRAPH in p.list_graphs():
        p.graph(Role.WRITER, GRAPH).delete()
    p.close()


def _count(pool: FalkorPool, query: str) -> int:
    return int(pool.run_sync(Role.WRITER, GRAPH, query, {}, read_only=True, timeout_ms=5000).rows[0][0])


def test_subprojects_load_idempotently(pool: FalkorPool) -> None:
    for text in (V1, V1, V2):
        sync_sigs(BatchWriter(pool, GRAPH, "t"), FakeGit(text), SHA, set())  # type: ignore[arg-type]
    assert _count(pool, "MATCH (:SIG)-[:HAS_SUBPROJECT]->(s:Subproject) RETURN count(s)") == 2
    assert _count(pool, "MATCH (s:Subproject) RETURN count(s)") == 2
    assert _count(pool, "MATCH (:Person)-[e:SUBPROJECT_LEAD]->(:Subproject) RETURN count(e)") == 2
    open_q = "MATCH (p:Person)-[e:SUBPROJECT_LEAD]->(:Subproject) WHERE e.valid_to = 4102444800 RETURN count(e)"
    assert _count(pool, open_q) == 1
    url_q = (
        "MATCH (s:Subproject {key: 'sig-apps/kubectl'}) "
        "WHERE s.url = 'https://github.com/kubernetes/kubectl' RETURN count(s)"
    )
    assert _count(pool, url_q) == 1
