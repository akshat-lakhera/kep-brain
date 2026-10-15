"""Per-user memory against FalkorDB, on throwaway `mem:` graphs that each test deletes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from ulid import ULID

from app.db.falkordb import FalkorPool, Role
from app.memory import store
from app.settings import Settings

ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
ANSWER = "Approved by the SIG leads [1]. UNIQUE-MODEL-SENTENCE"


@pytest_asyncio.fixture()
async def pool() -> AsyncIterator[FalkorPool]:
    p = FalkorPool(Settings(_env_file=ENV_FILE if ENV_FILE.exists() else None))  # type: ignore[call-arg]
    try:
        await p.ping()
    except Exception as exc:  # noqa: BLE001 - any connection problem skips the integration test
        pytest.skip(f"FalkorDB not reachable: {exc}")
    yield p
    p.close()


@pytest.fixture()
def memory_id() -> str:
    return str(ULID())


@pytest_asyncio.fixture(autouse=True)
async def cleanup(pool: FalkorPool, memory_id: str) -> AsyncIterator[None]:
    yield
    if f"mem:{memory_id}" in await pool.ping():
        pool.graph(Role.MEMORY, f"mem:{memory_id}").delete()


def ask(n: int, question: str = "Who approves KEP-4671?", abstained: bool = False) -> dict[str, Any]:
    return {
        "request_id": f"req-{n}",
        "question": question,
        "answer_markdown": ANSWER,
        "abstained": abstained,
        "citations": [
            {"label": "KEP", "key": "keps/sig-scheduling/4671-gang", "title": "KEP-4671", "url": "https://x/1"}
        ],
        "tool_calls": [{"name": "find_entities"}, {"name": "who_owns"}],
    }


async def test_reading_a_missing_memory_never_creates_the_graph(pool: FalkorPool, memory_id: str) -> None:
    mem = await store.get_memory(pool, memory_id)
    assert mem["exists"] is False and mem["recent_episodes"] == [] and mem["facts"] == []
    recalled = await store.recall(pool, memory_id, "Who approves KEP-4671?")
    assert recalled["recalled"] == []
    assert await store.forget(pool, memory_id) is False
    assert await store.forget_fact(pool, memory_id, "interest:sig-node") is False
    assert f"mem:{memory_id}" not in await pool.ping()


async def test_first_remember_creates_the_graph_and_is_idempotent(pool: FalkorPool, memory_id: str) -> None:
    assert await store.remember(pool, memory_id, ask(1)) is True
    assert await store.remember(pool, memory_id, ask(1)) is False
    mem = await store.get_memory(pool, memory_id)
    assert mem["episode_count"] == 1
    assert mem["recent_episodes"][0]["evidence_keys"] == ["KEP|keps/sig-scheduling/4671-gang"]
    assert {f["key"] for f in mem["facts"]} == {"entity_focus:kep-4671"}
    assert mem["facts"][0]["support_count"] == 1
    assert mem["procedures"][0]["tool_sequence"] == ["find_entities", "who_owns"]


async def test_recall_returns_question_kind_evidence_and_facts_but_no_answer_text(
    pool: FalkorPool, memory_id: str
) -> None:
    await store.remember(pool, memory_id, ask(1))
    await store.remember(pool, memory_id, ask(2, "And what about sig-node for v1.35?"))
    recalled = await store.recall(pool, memory_id, "Who owns KEP-4671?")
    assert [e["request_id"] for e in recalled["episodes"]] == ["req-2", "req-1"]
    assert {"request_id", "question", "question_kind", "evidence_keys", "created_at"} == set(recalled["episodes"][0])
    assert {f["key"] for f in recalled["facts"]} >= {"entity_focus:kep-4671", "interest:sig-node"}
    assert recalled["procedures"][0]["question_kind"] == "who_owns"
    assert "UNIQUE-MODEL-SENTENCE" not in json.dumps(recalled)
    assert "UNIQUE-MODEL-SENTENCE" not in store.planner_context(recalled)
    assert "UNIQUE-MODEL-SENTENCE" in json.dumps(await store.get_memory(pool, memory_id))  # the user's own view


async def test_abstained_answer_stores_no_summary_and_counts_a_failure(pool: FalkorPool, memory_id: str) -> None:
    await store.remember(pool, memory_id, ask(1, abstained=True))
    mem = await store.get_memory(pool, memory_id)
    assert mem["recent_episodes"][0]["answer_summary"] == ""
    assert (mem["procedures"][0]["success_count"], mem["procedures"][0]["failure_count"]) == (0, 1)


async def test_facts_accumulate_and_can_be_forgotten_one_by_one(pool: FalkorPool, memory_id: str) -> None:
    for n in (1, 2, 3):
        await store.remember(pool, memory_id, ask(n))
    facts = {f["key"]: f for f in (await store.get_memory(pool, memory_id))["facts"]}
    assert facts["entity_focus:kep-4671"]["support_count"] == 3
    assert facts["entity_focus:kep-4671"]["confidence"] == pytest.approx(0.8)
    assert await store.forget_fact(pool, memory_id, "entity_focus:kep-4671") is True
    assert (await store.get_memory(pool, memory_id))["facts"] == []
    assert await store.forget_fact(pool, memory_id, "entity_focus:kep-4671") is False


async def test_quota_compaction_keeps_the_newest_episodes(pool: FalkorPool, memory_id: str) -> None:
    for n in range(1, 6):
        await store.remember(pool, memory_id, ask(n))
    assert await store.compact(pool, memory_id, max_episodes=3) == 2
    mem = await store.get_memory(pool, memory_id)
    assert [e["request_id"] for e in mem["recent_episodes"]] == ["req-5", "req-4", "req-3"]
    assert await store.compact(pool, memory_id, max_episodes=3) == 0
    assert mem["facts"][0]["support_count"] == 5


async def test_forget_deletes_the_graph(pool: FalkorPool, memory_id: str) -> None:
    await store.remember(pool, memory_id, ask(1))
    assert await store.forget(pool, memory_id) is True
    assert f"mem:{memory_id}" not in await pool.ping()


async def test_playbook_recalled_listed_and_deleted(pool: FalkorPool, memory_id: str) -> None:
    await store.remember(pool, memory_id, ask(1))
    await store.remember(pool, memory_id, ask(2))
    recalled = await store.recall(pool, memory_id, "Who approves KEP-1234?")
    assert recalled["procedures"][0]["tool_sequence"] == ["find_entities", "who_owns"]
    assert recalled["procedures"][0]["success_count"] == 2
    assert "find_entities -> who_owns" in store.planner_context(recalled)
    mem = await store.get_memory(pool, memory_id)
    assert mem["playbooks"] == mem["procedures"] and mem["playbooks"][0]["observed_at"]
    key = mem["playbooks"][0]["key"]
    assert await store.forget_playbook(pool, memory_id, key) is True
    assert (await store.get_memory(pool, memory_id))["playbooks"] == []
