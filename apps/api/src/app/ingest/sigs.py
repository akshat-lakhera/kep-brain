"""Load `sigs.yaml` from the community clone: SIG / WorkingGroup / Committee + leadership (03 §4.1, §5.1).

`sigs.yaml` is a snapshot source (03 §7.6): leadership edges start at first
observation and are closed by set difference when a later fetch drops a person.
E-mail addresses in the file are never read into the graph (03 §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.db.batch import BatchWriter
from app.ingest.common import (
    COMMUNITY_REPO,
    Git,
    blob_url,
    is_bot,
    normalise_login,
    open_state_props,
    path_weight,
    person_url,
)
from app.ingest.kep_yaml import load_yaml

log = structlog.get_logger(__name__)
SIGS_PATH = "sigs.yaml"
GROUPS = (("sigs", "SIG"), ("workinggroups", "WorkingGroup"), ("committees", "Committee"))
LEAD_RELS = (("chairs", "CHAIRS"), ("tech_leads", "TECH_LEAD"), ("emeritus_leads", "EMERITUS_LEAD"))


@dataclass
class OrgChart:
    nodes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # label -> rows
    label_of: dict[str, str] = field(default_factory=dict)  # dir -> label
    leads: list[tuple[str, str, str, str]] = field(default_factory=list)  # (rel, login, label, dir)
    liaisons: list[tuple[str, str, str]] = field(default_factory=list)  # (login, label, dir)
    stakeholders: list[tuple[str, str]] = field(default_factory=list)  # (wg dir, sig dir)
    people: dict[str, str] = field(default_factory=dict)  # login -> raw


def parse_sigs_yaml(text: str, sha: str, in_scope: set[str]) -> OrgChart:
    data = load_yaml(text) or {}
    source = blob_url(COMMUNITY_REPO, sha, SIGS_PATH)
    chart = OrgChart()
    name_to_dir = {str(g.get("name")): str(g.get("dir")) for g in data.get("sigs") or [] if g.get("dir")}
    for group_key, label in GROUPS:
        rows: list[dict[str, Any]] = []
        for group in data.get(group_key) or []:
            gdir = group.get("dir")
            if not gdir:
                continue
            contact = group.get("contact") or {}
            charter = group.get("charter_link")
            row: dict[str, Any] = {
                "key": gdir,
                "name": gdir,
                "display_name": group.get("name"),
                "label": group.get("label"),
                "mission": (group.get("mission_statement") or "").strip() or None,
                "charter_url": f"https://github.com/{COMMUNITY_REPO}/blob/{sha}/{gdir}/{charter}" if charter else None,
                "slack_channel": f"#{contact['slack']}" if contact.get("slack") else None,
                "mailing_list_url": contact.get("mailing_list"),
                "github_teams": [t["name"] for t in contact.get("teams") or [] if t.get("name")] or None,
                "url": f"https://github.com/{COMMUNITY_REPO}/tree/{sha}/{gdir}",
                "source_url": source,
                "source_repo": COMMUNITY_REPO,
                "source_path": SIGS_PATH,
                "source_sha": sha,
            }
            if label == "SIG":
                row["in_scope"] = gdir in in_scope
            if label == "WorkingGroup":
                stake = [name_to_dir.get(str(n), str(n)) for n in group.get("stakeholder_sigs") or []]
                row["stakeholder_sigs"] = stake or None
                chart.stakeholders.extend((gdir, s) for s in stake)
            rows.append(row)
            chart.label_of[gdir] = label
            leadership = group.get("leadership") or {}
            for field_name, rel in LEAD_RELS:
                for person in leadership.get(field_name) or []:
                    login = normalise_login(person.get("github"))
                    if login:
                        chart.people.setdefault(login, str(person.get("github")))
                        chart.leads.append((rel, login, label, gdir))
            liaison = contact.get("liaison") or {}
            login = normalise_login(liaison.get("github")) if isinstance(liaison, dict) else None
            if login and label == "SIG":
                chart.people.setdefault(login, str(liaison.get("github")))
                chart.liaisons.append((login, label, gdir))
        chart.nodes[label] = rows
    return chart


def sync_sigs(writer: BatchWriter, git: Git, sha: str, in_scope: set[str]) -> OrgChart:
    text = git.read(sha, SIGS_PATH)
    if text is None:
        raise FileNotFoundError(f"{SIGS_PATH} missing at {sha}")
    chart = parse_sigs_yaml(text, sha, in_scope)
    source = blob_url(COMMUNITY_REPO, sha, SIGS_PATH)
    for label, rows in chart.nodes.items():
        writer.upsert_nodes(label, rows)
    writer.upsert_nodes(
        "Person",
        [
            {
                "key": login,
                "login": login,
                "login_raw": raw,
                "url": person_url(login),
                "is_bot": is_bot(login),
                "source_url": source,
            }
            for login, raw in chart.people.items()
        ],
    )
    writer.upsert_nodes(
        "Document",
        [
            {
                "key": f"{COMMUNITY_REPO}:{SIGS_PATH}",
                "kind": "sigs_yaml",
                "repo": COMMUNITY_REPO,
                "path": SIGS_PATH,
                "title": SIGS_PATH,
                "url": source,
                "source_url": source,
                "source_sha": sha,
                "byte_size": len(text.encode("utf-8")),
            }
        ],
    )
    t = writer.observed_at
    for _field, rel in LEAD_RELS:
        for label in ("SIG", "WorkingGroup", "Committee"):
            rows = [
                {
                    "from": login,
                    "to": gdir,
                    "props": {**open_state_props(t, source, "first_observed"), "w": path_weight(label)},
                }
                for r, login, lab, gdir in chart.leads
                if r == rel and lab == label
            ]
            _write_snapshot_edges(writer, rel, "Person", label, rows, chart, t)
    liaison_rows = [
        {"from": login, "to": gdir, "props": {**open_state_props(t, source, "first_observed"), "w": 4}}
        for login, _label, gdir in chart.liaisons
    ]
    _write_snapshot_edges(writer, "LIAISON", "Person", "SIG", liaison_rows, chart, t)
    stake_rows = [
        {"from": wg, "to": sig, "props": {**open_state_props(t, source, "first_observed"), "w": 4}}
        for wg, sig in chart.stakeholders
    ]
    _write_snapshot_edges(writer, "STAKEHOLDER", "WorkingGroup", "SIG", stake_rows, chart, t)
    log.info("sigs_loaded", **{label: len(rows) for label, rows in chart.nodes.items()}, people=len(chart.people))
    return chart


def _write_snapshot_edges(
    writer: BatchWriter,
    rel: str,
    from_label: str,
    to_label: str,
    rows: list[dict[str, Any]],
    chart: OrgChart,
    t: int,
) -> None:
    """Open edges for the current snapshot (keeping an existing open interval), close the ones that disappeared."""
    _open_snapshot_edges(writer, rel, from_label, to_label, rows)
    current = {(r["from"], r["to"]) for r in rows}
    for target_dir, label in chart.label_of.items():
        if label != to_label:
            continue
        writer.query(
            f"MATCH (a:{from_label})-[e:{rel}]->(b:{to_label} {{key: $k}}) "
            "WHERE e.valid_to = $open AND NOT a.key IN $current SET e.valid_to = $t",
            {
                "k": target_dir,
                "current": [f for f, to in current if to == target_dir],
                "open": open_state_props(t, "")["valid_to"],
                "t": t,
            },
        )


def _open_snapshot_edges(
    writer: BatchWriter, rel: str, from_label: str, to_label: str, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    for row in rows:
        row["props"]["observed_at"] = writer.observed_at
        row["props"]["sync_run_id"] = writer.sync_run_id
    writer.query(
        f"UNWIND $rows AS r MATCH (a:{from_label} {{key: r.from}}) MATCH (b:{to_label} {{key: r.to}}) "
        f"MERGE (a)-[e:{rel} {{valid_to: r.props.valid_to}}]->(b) "
        "ON CREATE SET e += r.props ON MATCH SET e.observed_at = r.props.observed_at, "
        "e.sync_run_id = r.props.sync_run_id",
        {"rows": rows},
    )
