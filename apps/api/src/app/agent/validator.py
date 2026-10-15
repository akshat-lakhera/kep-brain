"""Deterministic claim validator (02 §6.3, 03 §8.3). No LLM involved.

Rules:
1. Every evidence id the answer cites (inline `[[id]]` markers and each
   claim's `evidence_ids`) must come from a tool result of this request.
2. `Finding`, `Episode` and `Fact` ids are context, never citable.
3. `abstained = false` needs at least one claim with at least one valid id,
   and at least one inline citation. Claims are the reply's lines that carry
   markers (`parse_answer`); explicit references to returned records
   (`KEP-<n>`, `#<n>`, `@login`) are linked first (`link_mentions`).
4. Every URL in the Markdown must be the URL of a record returned in this
   request; other URLs are removed (the link text stays). `[[...]]` markers
   that hold no evidence id (e.g. a Finding key) are removed too.
Any violation of 1–3 turns the answer into an abstention
(`unsupported_claims`); the rejected text is never returned.
On success the `[[id]]` markers become `[n]` with a numbered citation list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.db.results import Evidence
from app.tools.base import NON_EVIDENCE_LABELS as UNCITABLE_LABELS

# `[[id]]` is the instructed form; a single-bracket `[id]` not followed by `(` is tolerated.
MARKER_RE = re.compile(r"\[\[\s*([a-z2-7]{12})\s*\]\]|\[([a-z2-7]{12})\](?!\()")
URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
# A double-bracket marker around something that is not an evidence id (a Finding or node key, a URL).
NON_ID_MARKER_RE = re.compile(r"\s*\[\[(?!\s*[a-z2-7]{12}\s*\]\])[^\[\]\n]{1,300}\]\]")


class Claim(BaseModel):
    text: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)


class FinalAnswer(BaseModel):
    answer_markdown: str = Field(default="", max_length=20000)
    claims: list[Claim] = Field(default_factory=list)
    abstained: bool = False
    abstain_reason: str | None = None


class Citation(BaseModel):
    index: int
    evidence_id: str
    label: str
    key: str
    title: str
    url: str


@dataclass
class Validated:
    answer_markdown: str
    citations: list[Citation]
    abstained: bool
    abstain_reason: str | None
    violations: list[str] = field(default_factory=list)
    nearest: list[Citation] = field(default_factory=list)


def _url_variants(url: str) -> set[str]:
    u = url.rstrip("/.,;:")
    return {u, u.split("#", 1)[0]}


def collect_row_urls(rows: Any, sink: set[str]) -> None:
    """URLs that appear as values in tool rows (e.g. a finding's a_url/b_url)."""
    if isinstance(rows, dict):
        for k, v in rows.items():
            if isinstance(v, str) and (k == "url" or k.endswith("_url")) and v.startswith("http"):
                sink.update(_url_variants(v))
            else:
                collect_row_urls(v, sink)
    elif isinstance(rows, list):
        for v in rows:
            collect_row_urls(v, sink)


_MULTI_RE = re.compile(r"\[\[?\s*[a-z2-7]{12}\s*\]?(?:\s*[,;]\s*\[?\s*[a-z2-7]{12}\s*\]?)+\s*\]?\]")
_NESTED_NUM_RE = re.compile(r"\[\s*((?:\[\d+\][,;\s]*)+)\]")


def normalise_markers(text: str) -> str:
    """`[[a, b]]`, `[a, b]` and `[[a], [b]]` → `[[a]][[b]]`, so every id is checked the same way."""

    def split(m: re.Match[str]) -> str:
        return "".join(f"[[{i}]]" for i in re.findall(r"[a-z2-7]{12}", m.group(0)))

    return _MULTI_RE.sub(split, text)


def _markers(text: str) -> list[str]:
    return [next(g for g in m.groups() if g) for m in MARKER_RE.finditer(text)]


_MENTION_RE = re.compile(
    r"\bKEP[-‐‑– ]?(\d{1,5})\b"  # KEP-583 (models also write non-breaking hyphens)
    r"|(?<![\w/])(?:kubernetes/enhancements)?#(\d{1,6})\b"  # #583, kubernetes/enhancements#5761
    r"|(?<![\w/@])@([A-Za-z0-9][A-Za-z0-9-]{0,38})"  # @login
)
_KEP_NUMBER_RE = re.compile(r"^keps/[^/]+/(\d+)-")
_TICKET_NUMBER_RE = re.compile(r"^kubernetes/enhancements#(\d+)$")


def link_mentions(text: str, evidence: dict[str, Evidence]) -> str:
    """Cite explicit references the answer makes to records returned in this request: `KEP-<n>`, `#<n>` (issue or
    PR) and `@login` get that record's marker right after the mention, unless the line already cites it. Only
    records some tool returned are linked, so nothing outside the request becomes citable."""
    targets: dict[tuple[str, str], str] = {}
    for eid, ev in evidence.items():
        if ev.label in UNCITABLE_LABELS:
            continue
        if ev.label == "KEP" and (m := _KEP_NUMBER_RE.match(ev.key)):
            targets.setdefault(("kep", m.group(1)), eid)
        elif ev.label in ("Issue", "PullRequest") and (m := _TICKET_NUMBER_RE.match(ev.key)):
            targets.setdefault(("ticket", m.group(1)), eid)
        elif ev.label == "Person":
            targets.setdefault(("person", ev.key.lower()), eid)

    def link_line(line: str) -> str:
        cited = set(_markers(normalise_markers(line)))
        out, last = [], 0
        for m in _MENTION_RE.finditer(line):
            kep, ticket, login = m.groups()
            key = ("kep", kep) if kep else ("ticket", ticket) if ticket else ("person", (login or "").lower())
            eid = targets.get(key)
            if eid is None or eid in cited or line[: m.start()].count("`") % 2:
                continue
            cited.add(eid)
            out.append(line[last : m.end()] + f" [[{eid}]]")
            last = m.end()
        return "".join(out) + line[last:]

    return "\n".join(link_line(line) for line in text.split("\n"))


_ABSTAIN_RE = re.compile(r"\A[^\w\n]*ABSTAIN(?:ED)?\b[^\w\n]*(no_evidence|out_of_scope)?[^\w\n]*", re.IGNORECASE)


def parse_answer(text: str) -> FinalAnswer:
    """The planner's plain-text reply as a FinalAnswer. A first line `ABSTAIN: <reason>` marks an abstention;
    each line that carries citation markers becomes one claim with those ids."""
    body = (text or "").strip()
    abstained, reason = False, None
    if m := _ABSTAIN_RE.match(body):
        abstained, reason = True, (m.group(1) or "no_evidence").lower()
        body = body[m.end() :].strip()
    claims = [
        Claim(text=line.strip()[:2000], evidence_ids=ids)
        for line in normalise_markers(body).splitlines()
        if (ids := list(dict.fromkeys(_markers(line))))
    ]
    return FinalAnswer(answer_markdown=body, claims=claims, abstained=abstained, abstain_reason=reason)


def _strip_unknown_urls(text: str, allowed: set[str]) -> tuple[str, int]:
    removed = 0

    def link(m: re.Match[str]) -> str:
        nonlocal removed
        if _url_variants(m.group(2)) & allowed:
            return m.group(0)
        removed += 1
        return m.group(1)

    text = MD_LINK_RE.sub(link, text)

    def bare(m: re.Match[str]) -> str:
        nonlocal removed
        if _url_variants(m.group(0)) & allowed:
            return m.group(0)
        removed += 1
        return ""

    # Bare URLs outside Markdown links.
    parts = re.split(r"(\[[^\]]*\]\([^)]*\))", text)
    for i in range(0, len(parts), 2):
        parts[i] = URL_RE.sub(bare, parts[i])
    return "".join(parts), removed


def validate(answer: FinalAnswer, evidence: dict[str, Evidence], row_urls: set[str]) -> Validated:
    citable = {eid: ev for eid, ev in evidence.items() if ev.label not in UNCITABLE_LABELS}
    violations: list[str] = []
    text, non_ids = NON_ID_MARKER_RE.subn("", normalise_markers(answer.answer_markdown or ""))

    inline = _markers(text)
    for eid in inline:
        if eid not in citable:
            violations.append(f"inline citation {eid} not produced by a tool in this request")
    for i, claim in enumerate(answer.claims):
        valid = [e for e in claim.evidence_ids if e in citable]
        if not valid:
            violations.append(f"claim {i} cites no evidence from this request")
        for e in claim.evidence_ids:
            if e not in citable:
                violations.append(f"claim {i} cites unknown or uncitable id {e}")

    if answer.abstained:
        # An abstention may still name the nearest existing records (ABS-10), but only
        # through ids seen in this request; anything else is dropped, never shown.
        nearest_ids = [e for e in dict.fromkeys(inline + [x for c in answer.claims for x in c.evidence_ids])]
        nearest = [e for e in nearest_ids if e in citable]
        if violations or not text.strip():
            return Validated("", [], True, answer.abstain_reason or "no_evidence", violations)
        md, cites = _number(text, citable)
        md, _ = _strip_unknown_urls(md, _allowed_urls(citable, row_urls))
        return Validated(md, cites, True, answer.abstain_reason or "no_evidence", [], _cites(nearest, citable))

    if not answer.claims:
        violations.append("answer has no claims")
    if not inline:
        violations.append("answer has no inline citations")
    if violations:
        return Validated("", [], True, "unsupported_claims", violations)

    md, cites = _number(text, citable)
    md, removed = _strip_unknown_urls(md, _allowed_urls(citable, row_urls))
    if removed:
        violations.append(f"removed {removed} URL(s) not returned by any tool")
    if non_ids:
        violations.append(f"removed {non_ids} citation marker(s) that hold no evidence id")
    return Validated(md, cites, False, None, violations)


def _allowed_urls(citable: dict[str, Evidence], row_urls: set[str]) -> set[str]:
    allowed = set(row_urls)
    for ev in citable.values():
        if ev.url:
            allowed.update(_url_variants(ev.url))
    return allowed


def _cites(ids: list[str], citable: dict[str, Evidence]) -> list[Citation]:
    return [
        Citation(index=i + 1, evidence_id=e, label=citable[e].label, key=citable[e].key,
                 title=citable[e].title, url=citable[e].url)
        for i, e in enumerate(ids)
    ]  # fmt: skip


def _number(text: str, citable: dict[str, Evidence]) -> tuple[str, list[Citation]]:
    order: dict[str, int] = {}

    def repl(m: re.Match[str]) -> str:
        eid = next(g for g in m.groups() if g)
        if eid not in citable:
            return ""
        if eid not in order:
            order[eid] = len(order) + 1
        return f"[{order[eid]}]"

    out = MARKER_RE.sub(repl, text)
    out = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", out)
    return out, _cites(list(order), citable)
