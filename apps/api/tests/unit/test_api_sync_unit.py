"""Sync-status parsing and release ordering helpers."""

from __future__ import annotations

import json

from app.api.changes import _release_order
from app.api.sync import _steps


def test_steps_json_round_trip_and_garbage() -> None:
    raw = json.dumps({"sync-docs": {"count": 238, "ms": 1200}, "bad": 3})
    assert _steps(raw) == {"sync-docs": {"count": 238, "ms": 1200}}
    assert _steps("not json") == {}
    assert _steps(None) == {}
    assert _steps("[1, 2]") == {}


def test_release_order_is_numeric() -> None:
    rows = [{"key": "v1.10"}, {"key": "v1.9"}, {"key": "v1.37"}, {"key": "v1.4"}]
    assert [r["key"] for r in sorted(rows, key=_release_order)] == ["v1.4", "v1.9", "v1.10", "v1.37"]
