"""An unreachable or silent FalkorDB is reported as `graph_unavailable`, never as a raw client error."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.db.falkordb import FalkorPool, Role
from app.errors import AppError
from app.settings import Settings


@pytest.fixture
def pool() -> FalkorPool:
    # Port 1 is never a FalkorDB; depending on the host it refuses or times out. Both must map the same way.
    settings = Settings(
        falkordb_host="127.0.0.1", falkordb_port=1, falkordb_password=SecretStr("x"), falkordb_timeout_seconds=0.3
    )
    return FalkorPool(settings)


def test_run_sync_reports_unavailable(pool: FalkorPool) -> None:
    with pytest.raises(AppError) as err:
        pool.run_sync(Role.READER, "kep", "RETURN 1", read_only=True, timeout_ms=100)
    assert err.value.code == "graph_unavailable"


def test_list_graphs_reports_unavailable(pool: FalkorPool) -> None:
    with pytest.raises(AppError) as err:
        pool.list_graphs()
    assert err.value.code == "graph_unavailable"
