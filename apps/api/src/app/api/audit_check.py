"""Human hand-check record for findings: `evals/audit-check.yaml` (05 §4.3.1).

A human records one verdict per finding key and commits the file; the API only
reads it, from the same evals directory as `questions.yaml`. A missing or empty
file means nothing has been hand-checked: zeros and nulls, never an error.
Entries with an unknown verdict are ignored.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.eval.questions import evals_dir

log = structlog.get_logger(__name__)

FILE_NAME = "audit-check.yaml"
VERDICTS = ("correct", "incorrect", "not_checked")
_cache: dict[Path, tuple[float, dict[str, dict[str, Any]]]] = {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def parse_verdicts(data: Any) -> dict[str, dict[str, Any]]:
    """`{finding key: {verdict, checked_by, checked_at, note}}` from the parsed YAML document."""
    entries = data.get("findings") if isinstance(data, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for entry in entries or []:
        if not isinstance(entry, dict) or not entry.get("key") or entry.get("verdict") not in VERDICTS:
            continue
        out[str(entry["key"])] = {
            "verdict": entry["verdict"],
            "checked_by": _text(entry.get("checked_by")),
            "checked_at": _text(entry.get("checked_at")),
            "note": _text(entry.get("note")),
        }
    return out


def load_verdicts(path: Path | None = None) -> dict[str, dict[str, Any]]:
    path = path or evals_dir() / FILE_NAME
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cached = _cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        verdicts = parse_verdicts(yaml.safe_load(path.read_text(encoding="utf-8")))
    except yaml.YAMLError as exc:
        log.warning("audit_check_unreadable", path=str(path), error=str(exc)[:200])
        verdicts = {}
    _cache[path] = (mtime, verdicts)
    return verdicts


def with_verdicts(findings: list[dict[str, Any]], verdicts: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    for f in findings:
        f["human_verdict"] = verdicts.get(f["key"])
    return findings


def hand_check_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """`hand_checked` counts correct + incorrect verdicts; `precision` is null until one exists."""
    verdicts = [(f.get("human_verdict") or {}).get("verdict") for f in findings]
    correct = verdicts.count("correct")
    checked = correct + verdicts.count("incorrect")
    return {"hand_checked": checked, "precision": {"correct": correct, "checked": checked} if checked else None}
