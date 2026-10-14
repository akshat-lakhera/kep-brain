"""Memory names, question analysis and the planner context rules (no database)."""

from __future__ import annotations

import pytest
from ulid import ULID

from app.errors import AppError
from app.memory.classify import facts_from_question, question_kind
from app.memory.store import memory_graph_name, planner_context, valid_memory_id


def test_memory_id_accepts_only_a_26_char_ulid() -> None:
    ulid = str(ULID())
    assert valid_memory_id(ulid) == ulid
    assert valid_memory_id(ulid.lower()) == ulid
    for bad in (None, "", ulid[:-1], ulid + "A", f"{ulid[:-1]}!", f"{ulid[:-3]}' )"):
        assert valid_memory_id(bad) is None


def test_graph_name_rejects_anything_but_a_ulid() -> None:
    ulid = str(ULID())
    assert memory_graph_name(ulid) == f"mem:{ulid}"
    for bad in ("kep", "ops", f"{ulid}x", f"{ulid[:-1]}\n", "../etc", ulid.lower()):
        with pytest.raises(AppError):
            memory_graph_name(bad)


@pytest.mark.parametrize(
    ("question", "kind"),
    [
        ("Who approves KEP-4671?", "who_owns"),
        ("Why was KEP-583 marked implementable?", "why_decided"),
        ("Which KEPs are stale or contradict their tracking issue?", "freshness"),
        ("What has changed since I last asked?", "whats_changed"),
        ("hello", "other"),
    ],
)
def test_question_kind(question: str, kind: str) -> None:
    assert question_kind(question) == kind


def test_facts_come_from_the_question_text() -> None:
    facts = {f.key: f for f in facts_from_question("Who approves KEP-4671 in sig-scheduling for v1.38?")}
    assert set(facts) == {"interest:sig-scheduling", "entity_focus:kep-4671", "context:release:v1.38"}
    assert facts["entity_focus:kep-4671"].value == "KEP-4671"
    assert facts_from_question("Tell me something") == []


def test_planner_context_has_no_answer_text() -> None:
    recalled = {
        "episodes": [
            {
                "request_id": "r1",
                "question": "Who approves KEP-4671?",
                "question_kind": "who_owns",
                "evidence_keys": ["KEP|keps/sig-scheduling/4671-gang"],
                "answer_summary": "SECRET MODEL TEXT",
            }
        ],
        "facts": [{"key": "interest:sig-node", "value": "sig-node"}],
    }
    text = planner_context(recalled)
    assert "Who approves KEP-4671?" in text and "interest:sig-node" in text
    assert "SECRET MODEL TEXT" not in text and "NOT evidence" in text
    assert planner_context({"episodes": [], "facts": []}) == ""
