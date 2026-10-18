"""The planner's scope rule for questions about KEP Brain itself, and the explain_process topic handling."""

from __future__ import annotations

import pytest

from app.agent.prompts import SYSTEM_PROMPT, brief, tool_spec
from app.tools.t03.process import PRODUCT_OPENING, SEARCH, ExplainProcess, is_product_topic, topic_term


def test_prompt_puts_kep_brain_questions_in_scope() -> None:
    assert "Questions about KEP Brain itself" in SYSTEM_PROMPT
    assert "are IN scope" in SYSTEM_PROMPT
    assert 'explain_process(topic="KEP Brain"' in SYSTEM_PROMPT
    assert '"kp brain"' in SYSTEM_PROMPT and '"this tool"' in SYSTEM_PROMPT
    assert "Read obvious typos as KEP or KEP Brain" in SYSTEM_PROMPT


def test_prompt_keeps_out_of_scope_for_other_projects() -> None:
    assert "or KEP Brain itself (another project such as Helm" in SYSTEM_PROMPT
    assert "out_of_scope" in SYSTEM_PROMPT


def test_explain_process_spec_mentions_kep_brain_in_its_brief() -> None:
    spec = tool_spec(ExplainProcess())
    description = spec["function"]["description"]
    assert "KEP Brain" in description
    assert description == brief(ExplainProcess.description)


@pytest.mark.parametrize(
    ("topic", "term"),
    [
        ("what is a KEP", "kep*"),
        ("status implementable", "status*|implementable*"),
        ("what is kp brain", "kep*|brain*"),
        ("explain me what is kepbrain", "kep*|brain*"),
        ("KEP Brain", "kep*|brain*"),
        ("what is it", None),
    ],
)
def test_topic_term(topic: str, term: str | None) -> None:
    assert topic_term(topic) == term


@pytest.mark.parametrize(
    ("topic", "product"),
    [
        ("KEP Brain", True),
        ("what is kp brain", True),
        ("what can this tool do", True),
        ("what is a KEP", False),
        ("status implementable", False),
    ],
)
def test_is_product_topic(topic: str, product: bool) -> None:
    assert is_product_topic(topic) is product


def test_search_covers_both_document_kinds() -> None:
    assert "d.kind IN ['process', 'product']" in SEARCH
    assert "{kind: 'product'}" in PRODUCT_OPENING
