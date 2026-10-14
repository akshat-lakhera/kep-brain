"""Tool parameter bounds, kep_ref parsing, evidence ids, template hygiene and the registry surfaces."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.agent.prompts import tool_spec
from app.db.results import evidence_id
from app.tools.cypher import unique_comprehension_vars
from app.tools.kepref import _coerce
from app.tools.registry import TOOLS, llm_tools, mcp_tools


def test_registry_surfaces() -> None:
    assert len(llm_tools()) == 14
    names = {t.name for t in mcp_tools()}
    assert len(names) == 13
    assert "recall_memory" not in names and "draft_stale_doc_issue" not in names and "get_graph_schema" in names


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(583, "583"), ("KEP-583", "KEP-583"), ("keps/sig-node/1287-in-place-update-pod-resources/kep.yaml",
      "keps/sig-node/1287-in-place-update-pod-resources"), ("583-coscheduling", "583-coscheduling")],
)  # fmt: skip
def test_kep_ref_accepts(raw: object, expected: str) -> None:
    assert _coerce(raw) == expected


@pytest.mark.parametrize("raw", ["", "drop graph", "keps/../../etc", True, 1.5, "583; MATCH (n) DELETE n"])
def test_kep_ref_rejects(raw: object) -> None:
    with pytest.raises(ValueError):
        _coerce(raw)


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("find_entities", {"query": "x"}),
        ("find_entities", {"query": "gang", "limit": 50}),
        ("find_entities", {"query": "gang", "kinds": ["Commit"]}),
        ("kep_relations", {"kep_ref": 4671, "depth": 4}),
        ("find_contradictions", {"limit": 7}),
        ("find_contradictions", {"kinds": ["made_up"]}),
        ("path_between", {"from_label": "Person", "from_key": "a", "to_label": "KEP", "to_key": "1", "max_len": 6}),
        ("whats_changed", {"since": "last week"}),
        ("who_owns", {}),
        ("who_owns", {"kep_ref": 1, "feature_gate": "X"}),
        ("draft_stale_doc_issue", {"finding_key": "MATCH (n) RETURN n"}),
        ("get_kep", {"kep_ref": 583, "extra": 1}),
        ("rank_people", {"limit": 100}),
    ],
)
def test_params_out_of_bounds_rejected(tool: str, params: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TOOLS[tool].Params.model_validate(params)


def test_evidence_id_shape_and_stability() -> None:
    a = evidence_id("KEP", "keps/sig-scheduling/583-coscheduling")
    assert re.fullmatch(r"[a-z2-7]{12}", a)
    assert a == evidence_id("KEP", "keps/sig-scheduling/583-coscheduling")
    assert a != evidence_id("Issue", "keps/sig-scheduling/583-coscheduling")


def test_templates_never_parameterise_limit() -> None:
    from app.tools.t03 import audit, find_entities, history

    templates = [*audit.CORPUS.values(), *audit.FOR_KEP.values(), *find_entities.FULLTEXT.values(),
                 *history.TRACE.values(), *history.CHANGED.values()]  # fmt: skip
    for t in templates:
        assert re.search(r"LIMIT \d+", t), t
        assert not re.search(r"(LIMIT|SKIP)\s+\$", t)


def test_comprehension_vars_made_unique() -> None:
    t = (
        "MATCH (k:KEP {key: $key}) RETURN k, [(p:Person)-[r:APPROVES]->(k) | {person: p, stage: r.stage}] AS a, "
        "[(p:Person)-[r:PRR_APPROVED]->(k) WHERE r.x = 'p' | p] AS b"
    )
    out = unique_comprehension_vars(t)
    assert "(p_0:Person)-[r_0:APPROVES]->(k)" in out and "{person: p_0, stage: r_0.stage}" in out
    assert "(p_1:Person)-[r_1:PRR_APPROVED]->(k) WHERE r_1.x = 'p' | p_1]" in out
    assert out.startswith("MATCH (k:KEP {key: $key}) RETURN k,")


def test_outer_yield_variable_not_renamed() -> None:
    t = "CALL x YIELD node RETURN node, [(node)-[g:A]->(f:F) | f] AS a, [(node)-[o:B]->(s:S) | s] AS b"
    out = unique_comprehension_vars(t)
    assert "[(node)-[g_0:A]->(f_0:F) | f_0]" in out and "[(node)-[o_1:B]->(s_1:S) | s_1]" in out


def test_llm_specs_are_provider_safe() -> None:
    for tool in llm_tools():
        spec = tool_spec(tool)["function"]["parameters"]
        text = str(spec)
        assert "$ref" not in text and "anyOf" not in text and "$defs" not in text
        assert spec["type"] == "object"
