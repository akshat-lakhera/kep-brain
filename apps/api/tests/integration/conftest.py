"""Every test under this directory needs a FalkorDB; mark it `integration` so CI can split the suites."""

from __future__ import annotations

from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.integration)
