"""Normalisation of kep.yaml values (recon 01 §3.4–§3.5 Q4–Q11)."""

from __future__ import annotations

import json

import pytest

from app.ingest.common import normalise_login
from app.ingest.kep_yaml import normalise_milestone, parse_date, parse_kep_yaml


@pytest.mark.parametrize(
    ("raw", "status", "reason"),
    [
        ("implemented", "implemented", None),
        ("implementable", "implementable", None),
        ("provisional", "provisional", None),
        ("withdrawn", "withdrawn", None),
        ("replaced", "replaced", None),
        ("rejected", "rejected", None),
        ("deferred", "deferred", None),
        ("imlpemented", "implemented", "status_typo"),
        ("superseded", "replaced", "status_not_in_enum"),
        ("implemented (alpha)", "implemented", "status_not_in_enum"),
        ("removed", "implemented", "status_not_in_enum"),
        ("Implemented", "implemented", None),
    ],
)
def test_status_map(raw: str, status: str, reason: str | None) -> None:
    meta = parse_kep_yaml(f"title: t\nstatus: {raw}\n")
    assert meta.status == status
    assert meta.status_raw == raw
    assert meta.metadata_invalid is (reason is not None)
    if reason:
        assert reason in meta.invalid_reasons


def test_status_removed_implies_stage_removed() -> None:
    meta = parse_kep_yaml("status: removed\n")
    assert meta.stage == "removed"


def test_template_status_is_invalid_and_absent() -> None:
    meta = parse_kep_yaml("status: provisional|implementable|implemented\nstage: alpha|beta|stable\n")
    assert meta.status is None
    assert meta.stage is None
    assert {"status_not_in_enum", "stage_not_in_enum", "template_text"} <= set(meta.invalid_reasons)


@pytest.mark.parametrize(
    ("raw", "stage"),
    [("alpha", "alpha"), ("beta", "beta"), ("stable", "stable"), ("alpha (deprecated)", "deprecated")],
)
def test_stage_map(raw: str, stage: str) -> None:
    assert parse_kep_yaml(f"stage: {raw}\n").stage == stage


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.31", "v1.31"),
        ("v1.31", "v1.31"),
        ('"1.9"', "v1.9"),
        ("v1.24.0", "v1.24"),
        ('"0.0"', None),
        ("TBD", None),
        ("never", None),
        ('""', None),
        ("x.y", None),
        ("TODO", None),
    ],
)
def test_milestones(raw: str, expected: str | None) -> None:
    meta = parse_kep_yaml(f"latest-milestone: {raw}\nmilestone:\n  stable: {raw}\n")
    assert meta.latest_milestone == expected
    assert meta.milestones.get("stable") == expected
    assert not meta.metadata_invalid


def test_milestone_unquoted_float() -> None:
    assert normalise_milestone(1.3) == "v1.3"
    assert normalise_milestone(None) is None


@pytest.mark.parametrize(
    ("raw", "iso", "bad"),
    [
        ("2018-09-06", "2018-09-06", False),
        ("2025-30-01", "2025-01-30", True),
        ("2023-14-05", "2023-05-14", True),
        ("not a date", None, True),
        (None, None, False),
    ],
)
def test_tolerant_dates(raw: str | None, iso: str | None, bad: bool) -> None:
    assert parse_date(raw) == (iso, bad)


def test_unparseable_date_does_not_break_the_file() -> None:
    meta = parse_kep_yaml("title: x\ncreation-date: 2025-30-01\nstatus: implementable\n")
    assert meta.parse_error is None
    assert meta.creation_date == "2025-01-30"
    assert meta.creation_date_raw == "2025-30-01"
    assert "creation_date_day_month_swapped" in meta.invalid_reasons


@pytest.mark.parametrize(
    ("raw", "login"),
    [
        ("@SergeyKanzhelev", "sergeykanzhelev"),
        ("'@sergeykanzhelev'", "sergeykanzhelev"),
        ("PatrickLang", "patricklang"),
        ("@foo # lead", "foo"),
        ("TBD", None),
        ("", None),
        ("two words", None),
        (None, None),
    ],
)
def test_login_normalisation(raw: str | None, login: str | None) -> None:
    assert normalise_login(raw) == login


def test_people_and_participating_sigs() -> None:
    meta = parse_kep_yaml(
        "owning-sig: sig-node\n"
        "authors: ['@A', '@b', '@a']\n"
        "approvers: '@sergeykanzhelev'\n"
        "reviewers: null\n"
        "participating-sigs: [sig-node, sig-scheduling, TBD, Kubelet garbage collection WG, wg-batch]\n"
    )
    assert meta.authors == ["a", "b"]
    assert meta.approvers == ["sergeykanzhelev"]
    assert meta.reviewers == []
    assert meta.participating_sigs == ["sig-scheduling", "wg-batch"]
    assert meta.participating_raw == ["TBD", "Kubelet garbage collection WG"]


def test_number_and_gates() -> None:
    meta = parse_kep_yaml(
        'kep-number: "4960"\nfeature-gates:\n  - name: ContainerStopSignals\n    components: [kubelet]\n  - name: X\n'
    )
    assert meta.number == 4960
    assert meta.feature_gates == ["ContainerStopSignals", "X"]
    assert meta.gate_components["ContainerStopSignals"] == ["kubelet"]
    assert parse_kep_yaml("kep-number: NNNN\n").number is None


def test_yaml_error_is_reported() -> None:
    meta = parse_kep_yaml("title: [unclosed\n")
    assert meta.parse_error
    assert "yaml_parse_error" in meta.invalid_reasons


def test_field_values_are_canonical() -> None:
    meta = parse_kep_yaml("status: implemented\napprovers: ['@b', '@a']\nmilestone:\n  beta: '1.30'\n")
    values = meta.field_values()
    assert values["status"] == "implemented"
    assert values["milestone.beta"] == "v1.30"
    assert values["approvers"] == json.dumps(["a", "b"], separators=(",", ":"))
    assert values["reviewers"] is None
