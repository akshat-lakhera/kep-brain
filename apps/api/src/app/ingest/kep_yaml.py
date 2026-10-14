"""Parse and normalise one `kep.yaml` (03 §4.3, recon 01 §3.4–§3.5 Q4–Q11).

The normaliser is pure: it takes the raw YAML text and returns a `KepMeta`.
Every normalisation that changes or drops a value is recorded in
`metadata_invalid_reasons`, and the raw strings are always kept.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import yaml

from app.ingest.common import normalise_login
from app.schema.labels import KEP_STAGES, KEP_STATUSES

# recon Q4: every status string in the census, mapped by hand.
STATUS_MAP: dict[str, tuple[str, str | None]] = {
    **{s: (s, None) for s in KEP_STATUSES},
    "imlpemented": ("implemented", "status_typo"),
    "implemeted": ("implemented", "status_typo"),
    "superseded": ("replaced", "status_not_in_enum"),
    "implemented (alpha)": ("implemented", "status_not_in_enum"),
    "removed": ("implemented", "status_not_in_enum"),
}
STAGE_MAP: dict[str, tuple[str, str | None]] = {
    **{s: (s, None) for s in KEP_STAGES},
    "alpha (deprecated)": ("deprecated", "stage_not_in_enum"),
    "ga": ("stable", "stage_not_in_enum"),
}
# `status: removed` means the feature was removed: implemented KEP at stage `removed` (recon D5).
STATUS_IMPLIES_STAGE = {"removed": "removed"}

MILESTONE_STAGES = ("alpha", "beta", "stable", "deprecated", "disabled", "removed")
PLACEHOLDERS = {"", "0.0", "tbd", "never", "todo", "x.y", "n/a", "none", "vx.y", "v0.0"}
_MILESTONE_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.\d+)?$")
_ORG_RE = re.compile(r"^(sig|wg|committee)-[a-z0-9-]+$")


class _NoDatesLoader(yaml.SafeLoader):
    """SafeLoader that keeps dates as strings, so `2025-30-01` does not abort the parse (recon Q5)."""


_NoDatesLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_NoDatesLoader)  # noqa: S506 - SafeLoader subclass


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    return value.strip() if isinstance(value, str) else str(value)


def normalise_milestone(raw: Any) -> str | None:
    """`1.31` / `"v1.31"` -> `v1.31`; placeholders and junk -> None."""
    text = _scalar(raw)
    if text is None or text.strip().lower() in PLACEHOLDERS:
        return None
    m = _MILESTONE_RE.match(text.strip())
    if not m:
        return None
    return f"v{int(m.group(1))}.{int(m.group(2))}"


def release_minor(release: str) -> int:
    return int(release.split(".")[1])


def parse_date(raw: Any) -> tuple[str | None, bool]:
    """Tolerant date parse: `yyyy-mm-dd`, then `yyyy-dd-mm` (recon Q5). Returns (iso, was_swapped_or_bad)."""
    text = _scalar(raw)
    if not text:
        return None, False
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text.strip())
    if not m:
        return None, True
    y, a, b = (int(x) for x in m.groups())
    for month, day, swapped in ((a, b, False), (b, a, True)):
        try:
            return date(y, month, day).isoformat(), swapped
        except ValueError:
            continue
    return None, True


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str | int | float):
        return [str(value)]
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return []


def _logins(value: Any) -> tuple[list[str], list[str]]:
    """(normalised unique logins in order, raw strings)."""
    raw = _str_list(value)
    out: list[str] = []
    for item in raw:
        login = normalise_login(item)
        if login and login not in out:
            out.append(login)
    return out, raw


@dataclass
class KepMeta:
    """Normalised `kep.yaml` content. `None` means absent (P5)."""

    title: str | None = None
    number: int | None = None
    number_raw: str | None = None
    owning_sig: str | None = None
    status: str | None = None
    status_raw: str | None = None
    stage: str | None = None
    stage_raw: str | None = None
    latest_milestone: str | None = None
    latest_milestone_raw: str | None = None
    milestones: dict[str, str] = field(default_factory=dict)
    milestones_raw: dict[str, str] = field(default_factory=dict)
    creation_date: str | None = None
    creation_date_raw: str | None = None
    last_updated: str | None = None
    last_updated_raw: str | None = None
    authors: list[str] = field(default_factory=list)
    authors_raw: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    approvers: list[str] = field(default_factory=list)
    editor: str | None = None
    participating_sigs: list[str] = field(default_factory=list)
    participating_raw: list[str] = field(default_factory=list)
    see_also_raw: list[str] = field(default_factory=list)
    replaces_raw: list[str] = field(default_factory=list)
    superseded_by_raw: list[str] = field(default_factory=list)
    feature_gates: list[str] = field(default_factory=list)
    gate_components: dict[str, list[str]] = field(default_factory=dict)
    disable_supported: bool | None = None
    metrics: list[str] = field(default_factory=list)
    invalid_reasons: list[str] = field(default_factory=list)
    parse_error: str | None = None

    @property
    def metadata_invalid(self) -> bool:
        return bool(self.invalid_reasons)

    def field_values(self) -> dict[str, str | None]:
        """Tracked fields for history diffs (03 §4.4 `StatusChange.field`), as canonical strings."""
        values: dict[str, str | None] = {
            "status": self.status,
            "stage": self.stage,
            "latest_milestone": self.latest_milestone,
        }
        for stage in MILESTONE_STAGES:
            values[f"milestone.{stage}"] = self.milestones.get(stage)
        lists = {
            "authors": self.authors,
            "approvers": sorted(self.approvers),
            "reviewers": sorted(self.reviewers),
            "participating_sigs": sorted(self.participating_sigs),
            "replaces": sorted(self.replaces_raw),
            "superseded_by": sorted(self.superseded_by_raw),
            "feature_gates": sorted(self.feature_gates),
        }
        for name, items in lists.items():
            values[name] = json.dumps(items, separators=(",", ":")) if items else None
        return values

    def raw_values(self) -> dict[str, str | None]:
        raw: dict[str, str | None] = {
            "status": self.status_raw,
            "stage": self.stage_raw,
            "latest_milestone": self.latest_milestone_raw,
        }
        for stage in MILESTONE_STAGES:
            raw[f"milestone.{stage}"] = self.milestones_raw.get(stage)
        return raw


def _add(meta: KepMeta, reason: str) -> None:
    if reason not in meta.invalid_reasons:
        meta.invalid_reasons.append(reason)


def parse_kep_yaml(text: str, sig_dir: str | None = None) -> KepMeta:
    """Normalise the raw text of a `kep.yaml`. `sig_dir` drops self-references in participating SIGs."""
    meta = KepMeta()
    try:
        data = load_yaml(text)
    except yaml.YAMLError as exc:
        meta.parse_error = str(exc).splitlines()[0]
        _add(meta, "yaml_parse_error")
        return meta
    if not isinstance(data, dict):
        meta.parse_error = "kep.yaml is not a mapping"
        _add(meta, "yaml_parse_error")
        return meta

    meta.title = _scalar(data.get("title"))
    number_raw = _scalar(data.get("kep-number"))
    meta.number_raw = number_raw
    if number_raw is not None and number_raw.strip().isdigit():
        meta.number = int(number_raw.strip())
    elif number_raw is not None:
        _add(meta, "kep_number_not_integer")
    meta.owning_sig = _scalar(data.get("owning-sig"))
    if meta.owning_sig and not _ORG_RE.match(meta.owning_sig):
        _add(meta, "owning_sig_invalid")

    status_raw = _scalar(data.get("status"))
    meta.status_raw = status_raw
    if status_raw is not None:
        key = status_raw.strip().lower()
        mapped = STATUS_MAP.get(key)
        if mapped is None:
            _add(meta, "status_not_in_enum")
        else:
            meta.status = mapped[0]
            if mapped[1]:
                _add(meta, mapped[1])
            implied = STATUS_IMPLIES_STAGE.get(key)
            if implied:
                meta.stage = implied

    stage_raw = _scalar(data.get("stage"))
    meta.stage_raw = stage_raw
    if stage_raw is not None and stage_raw.strip():
        mapped_stage = STAGE_MAP.get(stage_raw.strip().lower())
        if mapped_stage is None:
            _add(meta, "stage_not_in_enum")
        else:
            meta.stage = mapped_stage[0]
            if mapped_stage[1]:
                _add(meta, mapped_stage[1])

    lm_raw = _scalar(data.get("latest-milestone"))
    meta.latest_milestone_raw = lm_raw
    meta.latest_milestone = normalise_milestone(lm_raw)
    if lm_raw is not None and meta.latest_milestone is None and lm_raw.strip().lower() not in PLACEHOLDERS:
        _add(meta, "latest_milestone_unparseable")

    ms = data.get("milestone")
    if isinstance(ms, dict):
        for stage, value in ms.items():
            stage_key = str(stage).strip().lower()
            if stage_key not in MILESTONE_STAGES:
                _add(meta, "milestone_stage_unknown")
                continue
            raw = _scalar(value)
            if raw is None:
                continue
            meta.milestones_raw[stage_key] = raw
            norm = normalise_milestone(raw)
            if norm:
                meta.milestones[stage_key] = norm
            elif raw.strip().lower() not in PLACEHOLDERS:
                _add(meta, "milestone_unparseable")

    for attr, key in (("creation_date", "creation-date"), ("last_updated", "last-updated")):
        raw_date = _scalar(data.get(key))
        setattr(meta, f"{attr}_raw", raw_date)
        parsed, bad = parse_date(raw_date)
        setattr(meta, attr, parsed)
        if bad:
            _add(meta, f"{attr}_unparseable" if parsed is None else f"{attr}_day_month_swapped")

    meta.authors, meta.authors_raw = _logins(data.get("authors"))
    meta.reviewers, _ = _logins(data.get("reviewers"))
    meta.approvers, _ = _logins(data.get("approvers"))
    editor = data.get("editor")
    meta.editor = normalise_login(editor) if isinstance(editor, str) else None

    for item in _str_list(data.get("participating-sigs")):
        value = item.split("#", 1)[0].strip().lower()
        if _ORG_RE.match(value):
            if value != (meta.owning_sig or sig_dir) and value not in meta.participating_sigs:
                meta.participating_sigs.append(value)
        else:
            meta.participating_raw.append(item)

    meta.see_also_raw = _str_list(data.get("see-also"))
    meta.replaces_raw = _str_list(data.get("replaces"))
    meta.superseded_by_raw = _str_list(data.get("superseded-by"))

    gates = data.get("feature-gates")
    if isinstance(gates, list):
        for gate in gates:
            name = gate.get("name") if isinstance(gate, dict) else gate
            if not isinstance(name, str) or not re.match(r"^[A-Za-z][A-Za-z0-9]*$", name.strip()):
                continue
            name = name.strip()
            if name not in meta.feature_gates:
                meta.feature_gates.append(name)
            comps = gate.get("components") if isinstance(gate, dict) else None
            meta.gate_components[name] = [str(c).strip() for c in comps or [] if c]

    ds = data.get("disable-supported")
    meta.disable_supported = ds if isinstance(ds, bool) else None
    meta.metrics = _str_list(data.get("metrics"))
    if "|" in (status_raw or "") or "|" in (stage_raw or ""):
        _add(meta, "template_text")
    return meta
