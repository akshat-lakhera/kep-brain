"""Projection of FalkorDB values into JSON-safe rows and evidence (03 §3.2, §8.1)."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from falkordb import Node
from pydantic import BaseModel

# Properties that never leave the API (large or internal).
_HIDDEN = {"embedding", "content_hash", "raw_hash", "sync_run_id"}


def evidence_id(label: str, key: str) -> str:
    digest = hashlib.sha1(f"{label}|{key}".encode()).digest()
    return base64.b32encode(digest).decode("ascii").lower()[:12]


class Evidence(BaseModel):
    evidence_id: str
    label: str
    key: str
    title: str
    url: str


def primary_label(node: Node) -> str:
    labels = node.labels or []
    if isinstance(labels, str):
        return labels
    for lab in labels:
        if lab not in ("Ticket", "OwnersFile"):
            return str(lab)
    return str(labels[0]) if labels else "Node"


def node_title(label: str, props: dict[str, Any]) -> str:
    key = str(props.get("key", ""))
    if label == "KEP":
        num = props.get("number")
        title = props.get("title", key)
        return f"KEP-{num}: {title}" if num is not None else str(title)
    if label in ("Issue", "PullRequest"):
        return f"{key} {props.get('title', '')}".strip()
    if label == "StatusChange":
        before, after = props.get("from_value") or "∅", props.get("to_value") or "∅"
        return f"{props.get('field', '')} {before} → {after} ({str(props.get('at_iso', ''))[:10]})"
    if label == "Finding":
        return f"{props.get('kind', '')} on {props.get('kep_path', '')}"
    for field in ("title", "heading", "display_name", "name", "login", "summary"):
        if props.get(field):
            return str(props[field])[:160]
    return key


def node_evidence(node: Node) -> Evidence | None:
    props = node.properties or {}
    key = props.get("key")
    if not key:
        return None
    label = primary_label(node)
    url = props.get("url") or props.get("source_url") or ""
    return Evidence(
        evidence_id=evidence_id(label, str(key)),
        label=label,
        key=str(key),
        title=node_title(label, props),
        url=str(url),
    )
