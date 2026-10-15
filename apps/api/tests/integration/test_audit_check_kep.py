"""Hand-check fields on GET /v1/findings against the loaded `kep` graph (read-only)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db.falkordb import GRAPH_KEP, FalkorPool, Role
from app.main import create_app
from app.settings import Settings


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    pool = FalkorPool(Settings())
    try:
        loaded = (
            GRAPH_KEP in pool.list_graphs()
            and pool.run_sync(
                Role.READER, GRAPH_KEP, "MATCH (k:KEP) RETURN count(k)", read_only=True, timeout_ms=2000
            ).rows[0][0]
            >= 238
        )
    except Exception:  # noqa: BLE001
        loaded = False
    finally:
        pool.close()
    if not loaded:
        pytest.skip("graph `kep` is not loaded at the pinned data")
    with TestClient(create_app()) as c:
        yield c


def test_findings_hand_check_fields(client: TestClient) -> None:
    from app.api.audit_check import load_verdicts

    body = client.get("/v1/findings").json()
    recorded = load_verdicts()
    judged = [v for k, v in recorded.items() if v["verdict"] in ("correct", "incorrect")]
    assert body["summary"]["hand_checked"] == len(judged)
    if judged:
        assert body["summary"]["precision"]["checked"] == len(judged)
    else:
        assert body["summary"]["precision"] is None
    assert all("human_verdict" in f for f in body["items"])
    one = body["items"][0]
    detail = client.get(f"/v1/findings/{one['key']}").json()
    assert detail["human_verdict"] == one["human_verdict"]
