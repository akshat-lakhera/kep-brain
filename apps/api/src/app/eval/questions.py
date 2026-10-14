"""Locations and loaders for `evals/questions.yaml` and `evals/runs/*/summary.json`."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from app.errors import AppError


def evals_dir() -> Path:
    env = os.environ.get("EVALS_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[5] / "evals"


def load_questions(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or evals_dir() / "questions.yaml"
    if not path.is_file():
        raise AppError("not_found", {"reason": f"{path.name} not found"})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = data.get("questions") if isinstance(data, dict) else data
    return [q for q in records or [] if isinstance(q, dict) and q.get("id")]


def judge_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    judged = [q for q in questions if q.get("judge_order")]
    return sorted(judged, key=lambda q: q["judge_order"])


def public_question(q: dict[str, Any]) -> dict[str, Any]:
    return {"id": q["id"], "kind": q.get("kind"), "text": q.get("question"), "judge_order": q.get("judge_order")}


def run_dirs(runs: Path | None = None) -> list[Path]:
    runs = runs or evals_dir() / "runs"
    return sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []


def latest_summary() -> dict[str, Any]:
    for run in reversed(run_dirs()):
        summary = run / "summary.json"
        if summary.is_file():
            return {"run": run.name, **json.loads(summary.read_text(encoding="utf-8"))}
    raise AppError("not_found", {"reason": "no evaluation run recorded yet"})
