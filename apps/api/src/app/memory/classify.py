"""Deterministic question analysis: question kind (03 §11 `Procedure`) and `Fact`s taken from the question only."""

from __future__ import annotations

import re
from dataclasses import dataclass

QUESTION_KINDS = (
    "who_owns",
    "who_knows",
    "why_decided",
    "status_history",
    "whats_changed",
    "impact",
    "freshness",
    "path",
    "section_lookup",
    "other",
)

_KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("who_owns", re.compile(r"\b(who owns|owner of|owned by|who approves|approvers?|who reviews?|reviewers?)\b", re.I)),
    ("who_knows", re.compile(r"\b(who knows|who should i ask|expert|who worked on|who authored)\b", re.I)),
    ("why_decided", re.compile(r"\b(why (was|did|is|were)|who decided|decision|rationale|reason for)\b", re.I)),
    ("status_history", re.compile(r"\b(status history|history of|timeline|when did .* (change|become|move))\b", re.I)),
    ("whats_changed", re.compile(r"\b(what('s| has| have)? changed|since i last|recent changes|what is new)\b", re.I)),
    ("impact", re.compile(r"\b(impact|affected|depends on|depend on|blast radius|replaces|superseded)\b", re.I)),
    (
        "freshness",
        re.compile(r"\b(stale|out of date|contradict\w*|disagree\w*|inconsisten\w*|mismatch\w*|outdated)\b", re.I),
    ),
    ("path", re.compile(r"\b(path between|connected to|how is .* related|connection between)\b", re.I)),
    (
        "section_lookup",
        re.compile(r"\b(section|motivation|graduation criteria|risks and mitigations|test plan)\b", re.I),
    ),
)

_SIG = re.compile(r"\b(sig-[a-z]+(?:-[a-z]+)*)\b", re.I)
_KEP = re.compile(r"\bKEP[-\s#]?(\d{1,5})\b", re.I)
_RELEASE = re.compile(r"\bv?(1\.\d{2})\b")


@dataclass(frozen=True)
class FactCandidate:
    key: str
    kind: str
    value: str


def question_kind(question: str) -> str:
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(question):
            return kind
    return "other"


def facts_from_question(question: str) -> list[FactCandidate]:
    """Facts come from the user's own words, never from model-written text."""
    found: dict[str, FactCandidate] = {}
    for m in _SIG.finditer(question):
        sig = m.group(1).lower()
        found[f"interest:{sig}"] = FactCandidate(f"interest:{sig}", "interest", sig)
    for m in _KEP.finditer(question):
        number = m.group(1)
        found[f"entity_focus:kep-{number}"] = FactCandidate(
            f"entity_focus:kep-{number}", "entity_focus", f"KEP-{number}"
        )
    for m in _RELEASE.finditer(question):
        release = f"v{m.group(1)}"
        found[f"context:release:{release}"] = FactCandidate(f"context:release:{release}", "context", release)
    return list(found.values())[:10]


def kep_numbers(question: str) -> set[str]:
    return {m.group(1) for m in _KEP.finditer(question)}
