"""Hand-check record loader: schema, missing file, summary and per-finding verdicts."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.api import audit_check
from app.api.audit_check import hand_check_summary, load_verdicts, parse_verdicts, with_verdicts
from app.eval.questions import evals_dir

FILE = """
version: 1
findings:
  - key: fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling
    verdict: correct
    checked_by: team member (data)
    checked_at: 2026-10-16
    note: issue closed 2019, kep.yaml still provisional
  - key: fnd:stage_mismatch:keps/sig-node/1-x
    verdict: incorrect
    checked_by: team member (eval)
    checked_at: 2026-10-16
    note: label is stale, not kep.yaml
  - key: fnd:stage_mismatch:keps/sig-node/2-y
    verdict: not_checked
  - key: fnd:stage_mismatch:keps/sig-node/3-z
    verdict: maybe
  - verdict: correct
"""


def test_parse_keeps_known_verdicts_and_stringifies_dates() -> None:
    verdicts = parse_verdicts(yaml.safe_load(FILE))
    assert set(verdicts) == {
        "fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling",
        "fnd:stage_mismatch:keps/sig-node/1-x",
        "fnd:stage_mismatch:keps/sig-node/2-y",
    }
    first = verdicts["fnd:active_status_closed_issue:keps/sig-scheduling/583-coscheduling"]
    assert first == {
        "verdict": "correct",
        "checked_by": "team member (data)",
        "checked_at": "2026-10-16",
        "note": "issue closed 2019, kep.yaml still provisional",
    }
    assert verdicts["fnd:stage_mismatch:keps/sig-node/2-y"]["checked_by"] is None


def test_summary_counts_only_correct_and_incorrect() -> None:
    verdicts = parse_verdicts(yaml.safe_load(FILE))
    findings = [{"key": k} for k in [*verdicts, "fnd:unchecked:keps/x"]]
    with_verdicts(findings, verdicts)
    assert findings[-1]["human_verdict"] is None
    assert hand_check_summary(findings) == {"hand_checked": 2, "precision": {"correct": 1, "checked": 2}}


def test_no_verdicts_gives_zero_and_null() -> None:
    findings = with_verdicts([{"key": "fnd:a"}], {})
    assert hand_check_summary(findings) == {"hand_checked": 0, "precision": None}


def test_missing_and_broken_files_are_empty(tmp_path: Path) -> None:
    assert load_verdicts(tmp_path / "audit-check.yaml") == {}
    broken = tmp_path / "broken.yaml"
    broken.write_text("findings: [unclosed", encoding="utf-8")
    assert load_verdicts(broken) == {}
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_verdicts(empty) == {}


def test_loads_from_evals_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALS_DIR", str(tmp_path))
    audit_check._cache.clear()
    assert load_verdicts() == {}
    (tmp_path / "audit-check.yaml").write_text(FILE, encoding="utf-8")
    assert len(load_verdicts()) == 3


def test_repository_file_has_schema_and_no_invented_verdicts() -> None:
    path = evals_dir() / "audit-check.yaml"
    if not path.is_file():
        pytest.skip("evals/audit-check.yaml not mounted")
    text = path.read_text(encoding="utf-8")
    for field in ("verdict:", "checked_by:", "checked_at:", "note:", "correct | incorrect | not_checked"):
        assert field in text
    data = yaml.safe_load(text)
    assert isinstance(data, dict) and isinstance(data["findings"], list)
