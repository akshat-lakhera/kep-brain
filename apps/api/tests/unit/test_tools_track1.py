"""Track 1 tools (who_knows, impact_of_change, path_to_decision, changed_since): params, templates, registry."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from app.agent.prompts import tool_spec
from app.ingest import derive
from app.tools.cypher import unique_comprehension_vars
from app.tools.registry import TOOLS, llm_tools, mcp_tools
from app.tools.t01 import changed_since, decision_path, impact, who_knows

TRACK1 = ("who_knows", "impact_of_change", "path_to_decision", "changed_since")

TEMPLATES = [
    *who_knows.RANK.values(), who_knows.TERM_KEPS, who_knows.TERM_SECTIONS, who_knows.SIG_KEPS, who_knows.PAGERANK,
    *impact.REACH.values(), impact.ATTACH,
    decision_path.DIRECT, decision_path.VIA_KEP, decision_path.VIA_EVIDENCE, decision_path.LATEST_DECISION,
    *decision_path.SP.values(),
    *changed_since.CHANGES.values(), changed_since.RELEASE,
]  # fmt: skip


@pytest.mark.parametrize("name", TRACK1)
def test_registered_on_every_surface(name: str) -> None:
    assert name in {t.name for t in llm_tools()}
    assert name in {t.name for t in mcp_tools()}
    spec = str(tool_spec(TOOLS[name])["function"]["parameters"])
    assert "$ref" not in spec and "anyOf" not in spec and "$defs" not in spec


@pytest.mark.parametrize("template", TEMPLATES)
def test_templates_fixed_limit_and_read_only(template: str) -> None:
    assert re.search(r"LIMIT \d+", template), template
    assert not re.search(r"(LIMIT|SKIP)\s+\$", template)
    assert not re.search(r"\b(CREATE|MERGE|DELETE|SET|REMOVE)\b", template)


def test_who_knows_uses_pagerank_and_weights() -> None:
    # PageRank is computed once by the worker's derive step and read back as a Person property.
    assert "algo.pageRank(null, 'DECIDED_BY')" in derive.PAGERANK_Q and "node.pagerank" in derive.PAGERANK_Q
    assert "node.pagerank" in who_knows.PAGERANK and "algo." not in who_knows.PAGERANK
    rank = who_knows.RANK[10]
    for rel, weight in who_knows.WEIGHTS.items():
        assert f"WHEN '{rel}' THEN {weight}" in rank
    assert "coalesce(p.is_bot, false) = false" in rank


def test_impact_traverses_only_kep_and_gate_links() -> None:
    reach = impact.REACH[3]
    assert "*1..3" in reach and "*1..2" in impact.REACH[2]
    assert "REPLACES|SUPERSEDED_BY|SEE_ALSO|GATED_BY" in reach
    assert "NOT x.key IN $placeholders" in reach


def test_changed_since_template_comprehension_vars_unique() -> None:
    out = unique_comprehension_vars(changed_since.CHANGES[100])
    assert "(p_1:Person)-[:ACTED]->(c)" in out and "(p_2:Person)" in out


@pytest.mark.parametrize(
    ("tool", "params"),
    [
        ("who_knows", {}),
        ("who_knows", {"topic_or_kep": "!!"}),
        ("who_knows", {"sig": "sig node!"}),
        ("who_knows", {"sig": "sig-node", "limit": 7}),
        ("who_knows", {"sig": "sig-node", "metric": "betweenness"}),
        ("impact_of_change", {"kep_ref": 4671, "depth": 4}),
        ("impact_of_change", {"kep_ref": "583; MATCH (n) DELETE n"}),
        ("path_to_decision", {"person": "a b", "kep_ref": 583}),
        ("path_to_decision", {"person": "dom4ha", "kep_ref": 583, "path_count": 10}),
        ("path_to_decision", {"person": "dom4ha", "kep_ref": 583, "kinds": ["made_up"]}),
        ("changed_since", {"release": "last week"}),
        ("changed_since", {"release": "v1.36", "fields": ["labels"]}),
        ("changed_since", {"release": "v1.36", "limit": 1000}),
    ],
)
def test_params_rejected(tool: str, params: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TOOLS[tool].Params.model_validate(params)


def test_params_normalised() -> None:
    assert TOOLS["who_knows"].Params.model_validate({"topic_or_kep": 4671}).topic_or_kep == "4671"  # type: ignore[attr-defined]
    assert TOOLS["path_to_decision"].Params.model_validate({"person": "@Dom4ha", "kep_ref": 583}).person == "dom4ha"  # type: ignore[attr-defined]
    assert TOOLS["changed_since"].Params.model_validate({"release": "1.36"}).release == "v1.36"  # type: ignore[attr-defined]
