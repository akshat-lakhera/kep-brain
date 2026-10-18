"""The scheduled worker runs one coordination tick after each good sync (fakes only, no database)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.worker import __main__ as cli


class StopLoop(Exception):
    """Raised from the patched sleep to leave the scheduler's endless loop."""


class FakeWorker:
    fail_sync = False
    instances: list[FakeWorker] = []

    def __init__(self, *_: Any) -> None:
        self.pool = object()
        self.run_id = "run-1"
        self.closed = False
        FakeWorker.instances.append(self)

    def recorded_all(self) -> dict[str, Any]:
        if FakeWorker.fail_sync:
            raise RuntimeError("sync broke")
        return {}

    def close(self) -> None:
        self.closed = True


def run_schedule(
    monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True, key: str | None = "k", fail_sync: bool = False,
    tick_error: Exception | None = None,
) -> tuple[list[object], list[Any]]:  # fmt: skip
    settings = SimpleNamespace(findings_agent_enabled=enabled, openai_api_key=SecretStr(key) if key else None)
    ticks: list[object] = []
    beats: list[Any] = []

    def tick(s: object) -> dict[str, Any]:
        ticks.append(s)
        if tick_error is not None:
            raise tick_error
        return {"enqueued": {"triage_finding": 1}, "processed": {"freshness": {"done": 1}}}

    def sleep(_: float) -> None:
        raise StopLoop

    FakeWorker.fail_sync = fail_sync
    FakeWorker.instances = []
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda _: None)
    monkeypatch.setattr(cli, "Worker", FakeWorker)
    monkeypatch.setattr(cli, "heartbeat", lambda _pool, nxt: beats.append(nxt))
    monkeypatch.setattr(cli.time, "sleep", sleep)
    monkeypatch.setattr("app.worker.coordinate.run_coordination_tick", tick)
    with pytest.raises(StopLoop):
        cli.main(["schedule", "--interval-minutes", "1"])
    return ticks, beats


def test_tick_runs_after_a_good_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks, beats = run_schedule(monkeypatch)
    assert len(ticks) == 1
    assert len(beats) == 2 and beats[0] is None and beats[1] is not None
    assert FakeWorker.instances[0].closed


def test_tick_skipped_when_agent_disabled_or_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_schedule(monkeypatch, enabled=False)[0] == []
    assert run_schedule(monkeypatch, key=None)[0] == []


def test_tick_skipped_when_the_sync_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks, beats = run_schedule(monkeypatch, fail_sync=True)
    assert ticks == [] and len(beats) == 2


def test_tick_failure_keeps_the_heartbeat_and_the_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks, beats = run_schedule(monkeypatch, tick_error=RuntimeError("llm down"))
    assert len(ticks) == 1
    assert len(beats) == 2 and beats[1] is not None
    assert FakeWorker.instances[0].closed
