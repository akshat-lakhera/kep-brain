"""Template hygiene for FalkorDB 4.22 pattern comprehensions.

Observed on falkordb/falkordb:v4.22.0: when two pattern comprehensions in
one projection reuse a local variable name, e.g.
`[(p:Person)-[r:APPROVES]->(k) | p], [(p:Person)-[r:PRR_APPROVED]->(k) | p]`,
the later one returns an empty list. Templates are therefore rewritten once,
at import time, so that each comprehension's local variables get unique
names. Variables bound outside the comprehension are left alone.
"""

from __future__ import annotations

import re
from functools import lru_cache

# A variable declared in a pattern: `(n`, `(n:`, `[r:`; not a function call such as `type(r)`.
_DECL = re.compile(r"(?<![\w])\(\s*([A-Za-z_]\w*)\s*[:){\s]|\[\s*([A-Za-z_]\w*)\s*:|([A-Za-z_]\w*)\s*=\s*\(")
_AS = re.compile(r"\bAS\s+([A-Za-z_]\w*)", re.IGNORECASE)


def _comprehension_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        start = text.find("[(", i)
        if start < 0:
            return spans
        depth = 0
        for j in range(start, len(text)):
            ch = text[j]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    spans.append((start, j + 1))
                    i = j + 1
                    break
        else:
            return spans


def _decls(text: str) -> set[str]:
    return {name for groups in _DECL.findall(text) for name in groups if name}


def _strip_strings(text: str) -> str:
    return re.sub(r"'[^']*'", "''", text)


def _rename(body: str, old: str, new: str) -> str:
    """Rename a variable, skipping map keys (`{old: …}`, `, old: …`), properties and string literals."""
    out: list[str] = []
    last = 0
    in_string = [m.span() for m in re.finditer(r"'[^']*'", body)]
    for m in re.finditer(rf"(?<![\w.$]){re.escape(old)}\b", body):
        s, e = m.span()
        if any(a <= s < b for a, b in in_string):
            continue
        before = body[:s].rstrip()
        after = body[e:].lstrip()
        if after.startswith(":") and before.endswith(("{", ",")):
            continue
        out.append(body[last:s])
        out.append(new)
        last = e
    out.append(body[last:])
    return "".join(out)


@lru_cache(maxsize=512)
def unique_comprehension_vars(template: str) -> str:
    spans = _comprehension_spans(template)
    if len(spans) < 2:
        return template
    outer_text = "".join(
        template[a:b] for a, b in zip([0] + [e for _, e in spans], [s for s, _ in spans] + [len(template)], strict=True)
    )
    outer_text = _strip_strings(outer_text)
    # Any identifier used outside the comprehensions (pattern, YIELD, WITH, AS…) is bound there.
    outer = set(re.findall(r"(?<![\w.$])([A-Za-z_]\w*)", outer_text))
    out: list[str] = []
    last = 0
    for n, (a, b) in enumerate(spans):
        body = template[a:b]
        pattern_part = _strip_strings(body.split("|", 1)[0])
        local = {v for v in _decls(pattern_part) if v not in outer}
        for v in sorted(local, key=len, reverse=True):
            body = _rename(body, v, f"{v}_{n}")
        out.append(template[last:a])
        out.append(body)
        last = b
    out.append(template[last:])
    return "".join(out)
