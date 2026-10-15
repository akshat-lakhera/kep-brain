"""`kep_ref` resolution: a KEP number or a repository path (03 §15).

An ambiguous number (2133 exists twice) resolves to the candidate list
instead of a guess; the calling tool returns the candidates as its rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BeforeValidator, Field

from app.tools.base import Run

_NUM_RE = re.compile(r"^(?:kep[-\s#]?)?0*(\d{1,6})$", re.IGNORECASE)
_PATH_RE = re.compile(r"^keps/[a-z0-9-]+/[A-Za-z0-9._-]+$")
_DIR_RE = re.compile(r"^\d{1,6}-[A-Za-z0-9._-]+$")


def _coerce(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("kep_ref must be a KEP number or a path")
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str):
        raise ValueError("kep_ref must be a KEP number or a path")
    text = value.strip().rstrip("/")
    for suffix in ("/kep.yaml", "/README.md"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    if text.startswith("https://github.com/kubernetes/enhancements/"):
        m = re.search(r"(keps/[a-z0-9-]+/[A-Za-z0-9._-]+)", text)
        if m:
            text = m.group(1)
    if _NUM_RE.match(text) or _PATH_RE.match(text) or _DIR_RE.match(text):
        return text
    raise ValueError("kep_ref must be a KEP number or a repository path under keps/")


KepRef = Annotated[
    str,
    BeforeValidator(_coerce),
    Field(description="KEP number or repository path under keps/"),
]


@dataclass
class Resolved:
    key: str | None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return self.key is None and len(self.candidates) > 1


Q_BY_NUMBER = """
MATCH (k:KEP {number: $number})
RETURN k
ORDER BY k.key
LIMIT 10
"""

Q_BY_KEY = """
MATCH (k:KEP {key: $key})
RETURN k
LIMIT 1
"""

Q_BY_DIR = """
MATCH (k:KEP)
WHERE k.key ENDS WITH $suffix
RETURN k
ORDER BY k.key
LIMIT 10
"""


async def resolve_kep(run: Run, ref: str) -> Resolved:
    m = _NUM_RE.match(ref)
    if m:
        rows = await run.query(Q_BY_NUMBER, {"number": int(m.group(1))}, limit=10)
    elif ref.startswith("keps/"):
        rows = await run.query(Q_BY_KEY, {"key": ref}, limit=10)
    else:
        rows = await run.query(Q_BY_DIR, {"suffix": "/" + ref}, limit=10)
    run.truncated = False
    cands = [r["k"] for r in rows]
    if len(cands) == 1:
        return Resolved(key=cands[0]["key"], candidates=cands)
    return Resolved(key=None, candidates=cands)


def unresolved_rows(ref: str, res: Resolved) -> list[dict[str, Any]]:
    """Rows a tool returns when `kep_ref` does not resolve to exactly one KEP."""
    if res.ambiguous:
        return [{"ambiguous_reference": ref, "candidates": res.candidates}]
    return [{"not_found": ref}]
