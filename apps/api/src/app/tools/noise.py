"""Automation labels: label toggles made by bots and process tooling, not decisions.

`tracked/*` (enhancements-team tracking), `lgtm`, `approved`, `cncf-cla*` and `size/*` are excluded
from change feeds (`/v1/changes`, `whats_changed`) unless the caller asks for them (`include_labels`).
"""

from __future__ import annotations

AUTOMATION_LABEL_PREFIXES: tuple[str, ...] = ("tracked/", "size/", "cncf-cla")
AUTOMATION_LABELS: tuple[str, ...] = ("lgtm", "approved")


def is_automation_label(name: str) -> bool:
    return name in AUTOMATION_LABELS or name.startswith(AUTOMATION_LABEL_PREFIXES)


def automation_label_predicate(field: str = "c.field") -> str:
    """Cypher boolean: `field` is an automation label. Fixed text (no parameters)."""
    parts = [f"{field} STARTS WITH '{p}'" for p in AUTOMATION_LABEL_PREFIXES]
    parts += [f"{field} = '{name}'" for name in AUTOMATION_LABELS]
    return "(" + " OR ".join(parts) + ")"
