"""Person and SIG page helpers that need no graph."""

from __future__ import annotations

from app.api.people import _decision_role, _org_kind
from app.api.sigs import _people


def test_decision_role_order_is_fixed() -> None:
    assert _decision_role(["merger", "approver"]) == "approver, merger"
    assert _decision_role(["lgtm"]) == "lgtm"
    assert _decision_role(["zeta", "author"]) == "author, zeta"


def test_org_kind_prefers_known_labels() -> None:
    assert _org_kind(["SIG"]) == "SIG"
    assert _org_kind(["Other", "WorkingGroup"]) == "WorkingGroup"


def test_sig_people_leaders_first_then_by_kep_count() -> None:
    leaders = [{"login": "chair1", "url": "https://github.com/chair1", "rel": "CHAIRS"}]
    contributors = [
        {"login": "few", "url": "https://github.com/few", "rel": "REVIEWS", "keps": 1},
        {"login": "many", "url": "https://github.com/many", "rel": "AUTHORED", "keps": 5},
        {"login": "many", "url": "https://github.com/many", "rel": "APPROVES", "keps": 2},
        {"login": "chair1", "url": "https://github.com/chair1", "rel": "APPROVES", "keps": 9},
    ]
    people = _people(leaders, contributors)
    assert [p["login"] for p in people] == ["chair1", "many", "few"]
    assert people[0]["roles"] == ["chair", "approver"]
    assert people[1]["roles"] == ["author", "approver"]
