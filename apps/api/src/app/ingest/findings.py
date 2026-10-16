"""The five contradiction predicates (03 §7.5) and the `Finding` lifecycle (03 §4.7).

Every predicate compares two differently sourced records about one KEP, over current state only
(state edges and `StatusChange`s whose `valid_to` is the sentinel). Each hit becomes one `Finding`
keyed `fnd:<kind>:<KEP key>[:<successor key>]` carrying both sides with their public URLs.

Lifecycle on every run:
- new hit -> `state = open`, `reopened_count = 0`;
- hit that was `resolved_upstream` -> back to `open`, `reopened_count += 1`;
- other existing hit -> sides and `last_confirmed_at` refreshed, `state` untouched;
- existing finding whose predicate no longer holds -> `state = resolved_upstream` (a human
  `dismissed` verdict is kept).
Triage fields (`triage_*`, `assessment`, `action_draft_key`, `human_verdict`) are never written here.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.db.batch import BatchWriter
from app.ingest.common import iso
from app.ingest.kep_yaml import release_minor
from app.schema.labels import FINDING_KINDS, VALID_TO_OPEN

log = structlog.get_logger(__name__)

RULE_VERSION = 1
ACTIVE = ("provisional", "implementable")
TERMINAL = ("withdrawn", "rejected", "deferred", "replaced")
RELEASE_SIGNAL_LABELS = ("tracked/yes", "lead-opted-in")
MILESTONE_FIELDS = ("alpha", "beta", "stable", "deprecated", "disabled", "removed")
KEEP_STATES_WHEN_GONE = ("resolved_upstream", "dismissed")

_KEP_OK = "coalesce(k.stub, false) = false AND coalesce(k.archived, false) = false"


@dataclass
class Hit:
    kind: str
    kep_key: str
    a_label: str
    a_value: str
    a_url: str
    b_label: str
    b_value: str
    b_url: str
    suggested_fix: str
    successor_key: str | None = None
    evidence: list[tuple[str, str, str, str]] = field(default_factory=list)  # (label, key, kind, url)

    @property
    def key(self) -> str:
        base = f"fnd:{self.kind}:{self.kep_key}"
        return f"{base}:{self.successor_key}" if self.successor_key else base

    def sides(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "kep_path": self.kep_key,
            "rule_version": RULE_VERSION,
            "a_label": self.a_label,
            "a_value": self.a_value,
            "a_url": self.a_url,
            "b_label": self.b_label,
            "b_value": self.b_value,
            "b_url": self.b_url,
            "suggested_fix": self.suggested_fix,
            "successor_path": self.successor_key,
            "source_url": self.a_url,
            "source_repo": "kubernetes/enhancements",
        }


def kep_name(number: int | None, key: str) -> str:
    return f"KEP-{number}" if number is not None else key


def yaml_url(doc_url: str | None, kep: dict[str, Any]) -> str:
    return str(doc_url or kep.get("source_url") or kep.get("url") or "")


def _doc_evidence(doc_key: str | None, kep_key: str, url: str) -> tuple[str, str, str, str]:
    if doc_key:
        return ("Document", doc_key, "kep_yaml", url)
    return ("KEP", kep_key, "kep_yaml", url)


# -- predicate 1: active_status_closed_issue -----------------------------------------------


def suggested_fix_for_closed(state_reason: str | None) -> str:
    if state_reason == "completed":
        return "set_status_implemented"
    if state_reason == "not_planned":
        return "set_status_withdrawn_or_deferred"
    return "other"


_Q_ACTIVE = f"""
MATCH (k:KEP)-[t:TRACKED_BY]->(i:Issue)
WHERE t.valid_to = $open AND k.status IN $active AND i.state = 'closed' AND {_KEP_OK}
OPTIONAL MATCH (k)-[:HAS_DOCUMENT]->(d:Document {{kind: 'kep_yaml'}})
OPTIONAL MATCH (k)-[:CHANGED]->(sc:StatusChange {{kind: 'metadata', field: 'status'}})
WHERE sc.valid_to = $open
RETURN k.key, k.number, k.status, k.source_url, k.url, d.key, d.url,
       i.key, i.number, i.state_reason, i.closed_at_iso, i.url, sc.key, sc.source_url
"""


def hits_active_status_closed_issue(writer: BatchWriter) -> list[Hit]:
    hits = []
    for r in writer.query(_Q_ACTIVE, {"open": VALID_TO_OPEN, "active": list(ACTIVE)}):
        kep = {"source_url": r[3], "url": r[4]}
        a_url = yaml_url(r[6], kep)
        reason = r[9]
        closed = (r[10] or "")[:10]
        evidence = [_doc_evidence(r[5], r[0], a_url), ("Issue", r[7], "tracking_issue", r[11])]
        if r[12]:
            evidence.append(("StatusChange", r[12], "status_change", r[13] or a_url))
        hits.append(
            Hit(
                kind="active_status_closed_issue",
                kep_key=r[0],
                a_label="kep.yaml status",
                a_value=str(r[2]),
                a_url=a_url,
                b_label=f"issue #{r[8]} state",
                b_value=f"closed ({reason or 'no reason'})" + (f" on {closed}" if closed else ""),
                b_url=str(r[11]),
                suggested_fix=suggested_fix_for_closed(reason),
                evidence=evidence,
            )
        )
    return hits


# -- predicate 2: terminal_status_future_targets -------------------------------------------

_Q_TERMINAL_TARGETS = f"""
MATCH (k:KEP) WHERE k.status IN $terminal AND {_KEP_OK}
OPTIONAL MATCH (k)-[l:LATEST]->(lr:Release) WHERE l.valid_to = $open
OPTIONAL MATCH (k)-[t:TARGETS]->(r:Release) WHERE t.valid_to = $open
OPTIONAL MATCH (k)-[:HAS_DOCUMENT]->(d:Document {{kind: 'kep_yaml'}})
RETURN k.key, k.number, k.status, k.source_url, k.url, d.key, d.url,
       coalesce(lr.key, k.latest_milestone), lr.ordinal, t.stage, r.key, r.ordinal, r.is_future,
       [k.milestone_alpha, k.milestone_beta, k.milestone_stable, k.milestone_deprecated,
        k.milestone_disabled, k.milestone_removed]
"""

_Q_TERMINAL_SIGNALS = f"""
MATCH (k:KEP)-[t:TRACKED_BY]->(i:Issue {{state: 'open'}})
WHERE t.valid_to = $open AND k.status IN $terminal AND {_KEP_OK}
OPTIONAL MATCH (i)-[l:LABELED]->(lab:Label) WHERE l.valid_to = $open AND lab.key IN $signals
OPTIONAL MATCH (i)-[m:MILESTONED]->(r:Release {{is_future: true}}) WHERE m.valid_to = $open
RETURN k.key, i.key, i.number, i.url, collect(DISTINCT lab.key), collect(DISTINCT r.key)
"""


def future_targets(
    latest_key: str | None,
    latest_ordinal: int | None,
    targets: dict[str, tuple[str, int | None, bool | None]],
    future_releases: set[str],
) -> dict[str, str]:
    """stage -> release for targets that are future (`is_future`) or beyond the KEP's own latest milestone."""
    latest_ord = latest_ordinal if latest_ordinal is not None else release_minor(latest_key)
    out = {}
    for stage, (rkey, ordinal, is_future) in targets.items():
        ordv = ordinal if ordinal is not None else release_minor(rkey)
        future = bool(is_future) if is_future is not None else rkey in future_releases
        if future or (latest_ord is not None and ordv is not None and ordv > latest_ord):
            out[stage] = rkey
    return out


def hits_terminal_status_future_targets(writer: BatchWriter) -> list[Hit]:
    params = {"open": VALID_TO_OPEN, "terminal": list(TERMINAL)}
    future_releases = {str(r[0]) for r in writer.query("MATCH (r:Release {is_future: true}) RETURN r.key")}
    keps: dict[str, dict[str, Any]] = {}
    for r in writer.query(_Q_TERMINAL_TARGETS, params):
        kep = keps.setdefault(
            r[0],
            {"number": r[1], "status": r[2], "doc_key": r[5],
             "a_url": yaml_url(r[6], {"source_url": r[3], "url": r[4]}),
             "latest": r[7], "latest_ord": r[8], "targets": {}},
        )  # fmt: skip
        if r[9] and r[10]:
            kep["targets"][str(r[9])] = (str(r[10]), r[11], r[12])
        for stage, value in zip(MILESTONE_FIELDS, r[13] or [], strict=False):
            if value and stage not in kep["targets"]:
                kep["targets"][stage] = (str(value), None, None)
    signals: dict[str, tuple[str, int, str, list[str], list[str]]] = {}
    for r in writer.query(_Q_TERMINAL_SIGNALS, params | {"signals": list(RELEASE_SIGNAL_LABELS)}):
        labels = sorted(x for x in r[4] if x)
        milestones = sorted(x for x in r[5] if x)
        if labels or milestones:
            signals[r[0]] = (r[1], r[2], r[3], labels, milestones)
    hits = []
    for key, kep in sorted(keps.items()):
        fut = future_targets(kep["latest"], kep["latest_ord"], kep["targets"], future_releases)
        sig = signals.get(key)
        if not fut and not sig:
            continue
        evidence = [_doc_evidence(kep["doc_key"], key, kep["a_url"])]
        parts = [f"milestone.{s} = {v}" for s, v in sorted(fut.items(), key=lambda x: MILESTONE_FIELDS.index(x[0]))]
        b_label, b_url = "kep.yaml future targets", kep["a_url"]
        if sig:
            ikey, inum, iurl, labels, milestones = sig
            evidence.append(("Issue", ikey, "tracking_issue", iurl))
            parts.append(
                f"issue #{inum} open"
                + "".join(f", {lab}" for lab in labels)
                + "".join(f", milestone {m}" for m in milestones)
            )
            if not fut:
                b_label, b_url = f"issue #{inum} release-team signals", iurl
        hits.append(
            Hit(
                kind="terminal_status_future_targets",
                kep_key=key,
                a_label="kep.yaml status",
                a_value=str(kep["status"]),
                a_url=kep["a_url"],
                b_label=b_label,
                b_value="; ".join(parts),
                b_url=b_url,
                suggested_fix="remove_future_milestones" if fut else "other",
                evidence=evidence,
            )
        )
    return hits


# -- predicate 3: one_sided_replacement ----------------------------------------------------

_Q_ONE_SIDED = """
MATCH (s:KEP)-[r:REPLACES]->(p:KEP)
WHERE r.valid_to = $open AND coalesce(p.stub, false) = false AND coalesce(p.archived, false) = false
  AND coalesce(s.archived, false) = false
OPTIONAL MATCH (p)-[sb:SUPERSEDED_BY]->(s) WHERE sb.valid_to = $open AND coalesce(sb.derived, false) = false
WITH s, p, r, count(sb) AS declared
WHERE declared = 0
OPTIONAL MATCH (s)-[:HAS_DOCUMENT]->(sd:Document {kind: 'kep_yaml'})
OPTIONAL MATCH (p)-[:HAS_DOCUMENT]->(pd:Document {kind: 'kep_yaml'})
RETURN s.key, s.number, s.source_url, s.url, sd.key, sd.url, r.raw,
       p.key, p.number, p.source_url, p.url, pd.key, pd.url
"""


def hits_one_sided_replacement(writer: BatchWriter) -> list[Hit]:
    hits = []
    for r in writer.query(_Q_ONE_SIDED, {"open": VALID_TO_OPEN}):
        s_url = yaml_url(r[5], {"source_url": r[2], "url": r[3]})
        p_url = yaml_url(r[12], {"source_url": r[9], "url": r[10]})
        hits.append(
            Hit(
                kind="one_sided_replacement",
                kep_key=r[7],
                successor_key=r[0],
                a_label=f"{kep_name(r[1], r[0])} kep.yaml replaces",
                a_value=str(r[6] or r[7]),
                a_url=s_url,
                b_label=f"{kep_name(r[8], r[7])} kep.yaml superseded-by",
                b_value=f"does not list {kep_name(r[1], r[0])}",
                b_url=p_url,
                suggested_fix="add_superseded_by",
                evidence=[
                    _doc_evidence(r[11], r[7], p_url),
                    _doc_evidence(r[4], r[0], s_url),
                    ("KEP", r[0], "kep_yaml", s_url),
                ],
            )
        )
    return hits


# -- predicate 4: stage_mismatch -----------------------------------------------------------------

_Q_STAGE = f"""
MATCH (k:KEP)-[t:TRACKED_BY]->(i:Issue {{state: 'closed'}})
WHERE t.valid_to = $open AND k.stage IS NOT NULL AND {_KEP_OK}
OPTIONAL MATCH (i)-[l:LABELED]->(lab:Label) WHERE l.valid_to = $open AND lab.key STARTS WITH 'stage/'
OPTIONAL MATCH (k)-[:HAS_DOCUMENT]->(d:Document {{kind: 'kep_yaml'}})
RETURN k.key, k.number, k.stage, k.source_url, k.url, d.key, d.url, i.key, i.number, i.url,
       collect(DISTINCT lab.key)
"""


def stage_conflicts(kep_stage: str, stage_labels: Sequence[str]) -> bool:
    """Fires only when the closed issue carries stage labels and none of them is the kep.yaml stage."""
    stages = {lab.removeprefix("stage/") for lab in stage_labels if lab}
    return bool(stages) and kep_stage not in stages


def hits_stage_mismatch(writer: BatchWriter) -> list[Hit]:
    hits = []
    for r in writer.query(_Q_STAGE, {"open": VALID_TO_OPEN}):
        labels = sorted(x for x in r[10] if x)
        if not stage_conflicts(str(r[2]), labels):
            continue
        a_url = yaml_url(r[6], {"source_url": r[3], "url": r[4]})
        hits.append(
            Hit(
                kind="stage_mismatch",
                kep_key=r[0],
                a_label="kep.yaml stage",
                a_value=str(r[2]),
                a_url=a_url,
                b_label=f"issue #{r[8]} stage label (closed)",
                b_value=", ".join(labels),
                b_url=str(r[9]),
                suggested_fix="update_stage",
                evidence=[_doc_evidence(r[5], r[0], a_url), ("Issue", r[7], "tracking_issue", r[9])],
            )
        )
    return hits


# -- predicate 5: milestone_mismatch -------------------------------------------------------------

_Q_MILESTONE = f"""
MATCH (k:KEP)-[t:TRACKED_BY]->(i:Issue)-[m:MILESTONED]->(b:Release)
WHERE t.valid_to = $open AND m.valid_to = $open AND {_KEP_OK}
OPTIONAL MATCH (k)-[l:LATEST]->(a:Release) WHERE l.valid_to = $open
WITH k, i, b, coalesce(a.key, k.latest_milestone) AS latest
WHERE latest IS NOT NULL AND latest <> b.key
OPTIONAL MATCH (k)-[:HAS_DOCUMENT]->(d:Document {{kind: 'kep_yaml'}})
RETURN k.key, k.number, latest, k.source_url, k.url, d.key, d.url, i.key, i.number, i.state, i.url, b.key
"""


def hits_milestone_mismatch(writer: BatchWriter) -> list[Hit]:
    hits = []
    for r in writer.query(_Q_MILESTONE, {"open": VALID_TO_OPEN}):
        a_url = yaml_url(r[6], {"source_url": r[3], "url": r[4]})
        hits.append(
            Hit(
                kind="milestone_mismatch",
                kep_key=r[0],
                a_label="kep.yaml latest-milestone",
                a_value=str(r[2]),
                a_url=a_url,
                b_label=f"issue #{r[8]} milestone",
                b_value=f"{r[11]} (issue {r[9]})",
                b_url=str(r[10]),
                suggested_fix="update_latest_milestone",
                evidence=[_doc_evidence(r[5], r[0], a_url), ("Issue", r[7], "tracking_issue", r[10])],
            )
        )
    return hits


PREDICATES = {
    "active_status_closed_issue": hits_active_status_closed_issue,
    "terminal_status_future_targets": hits_terminal_status_future_targets,
    "one_sided_replacement": hits_one_sided_replacement,
    "stage_mismatch": hits_stage_mismatch,
    "milestone_mismatch": hits_milestone_mismatch,
}
assert tuple(PREDICATES) == FINDING_KINDS


# -- lifecycle ---------------------------------------------------------------------------------


@dataclass
class FindingUpdate:
    key: str
    props: dict[str, Any]


def plan_lifecycle(
    hits: Sequence[Hit], existing: dict[str, tuple[str, int]], now: int
) -> tuple[list[FindingUpdate], list[str], dict[str, int]]:
    """Return (rows to write for hits, keys to mark resolved_upstream, transition counts)."""
    counts = {"created": 0, "reopened": 0, "confirmed": 0, "resolved": 0}
    updates: list[FindingUpdate] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.key in seen:
            continue
        seen.add(hit.key)
        props = hit.sides() | {"last_confirmed_at": now, "last_confirmed_at_iso": iso(now)}
        if hit.key not in existing:
            props |= {"state": "open", "reopened_count": 0, "detected_at": now, "detected_at_iso": iso(now)}
            counts["created"] += 1
        else:
            state, reopened = existing[hit.key]
            if state == "resolved_upstream":
                props |= {
                    "state": "open",
                    "reopened_count": reopened + 1,
                    "reopened_at": now,
                    "reopened_at_iso": iso(now),
                }
                counts["reopened"] += 1
            else:
                counts["confirmed"] += 1
        updates.append(FindingUpdate(hit.key, props))
    resolved = sorted(k for k, (state, _) in existing.items() if k not in seen and state not in KEEP_STATES_WHEN_GONE)
    counts["resolved"] = len(resolved)
    return updates, resolved, counts


def _write(writer: BatchWriter, hits: Sequence[Hit], updates: Sequence[FindingUpdate], resolved: Sequence[str]) -> None:
    now, run = writer.observed_at, writer.sync_run_id
    rows = [{"key": u.key, "props": {k: v for k, v in u.props.items() if v is not None}} for u in updates]
    rows = list({r["key"]: r for r in rows}.values())
    for i in range(0, len(rows), 500):
        # MANDATORY constraints are checked at creation, so new findings are CREATEd with their required properties.
        writer.query(
            "UNWIND $rows AS r OPTIONAL MATCH (m:Finding {key: r.key}) WITH r, m WHERE m IS NULL "
            "CREATE (f:Finding {key: r.key, source_url: r.props.source_url, observed_at: $now, kind: r.props.kind, "
            "kep_path: r.props.kep_path, state: r.props.state, rule_version: r.props.rule_version}) "
            "SET f.first_seen_at = $now",
            {"rows": rows[i : i + 500], "now": now},
        )
        writer.query(
            "UNWIND $rows AS r MERGE (f:Finding {key: r.key}) "
            "ON CREATE SET f.first_seen_at = $now "
            "SET f += r.props, f.observed_at = $now, f.sync_run_id = $run",
            {"rows": rows[i : i + 500], "now": now, "run": run},
        )
    if resolved:
        writer.query(
            "UNWIND $keys AS k MATCH (f:Finding {key: k}) "
            "SET f.state = 'resolved_upstream', f.resolved_at = $now, f.resolved_at_iso = $iso, "
            "f.observed_at = $now, f.sync_run_id = $run",
            {"keys": list(resolved), "now": now, "iso": iso(now), "run": run},
        )
    unique = {h.key: h for h in hits}
    writer.upsert_edges(
        "ABOUT", "Finding", "KEP", [{"from": k, "to": h.kep_key, "props": {"w": 1}} for k, h in unique.items()]
    )
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for k, h in unique.items():
        for label, target, kind, url in h.evidence:
            if target:
                by_label[label].append(
                    {"from": k, "to": target, "props": {"evidence_kind": kind, "source_url": url, "w": 1}}
                )
    for label, erows in by_label.items():
        writer.upsert_edges("EVIDENCED_BY", "Finding", label, erows, identity=["evidence_kind"])


def detect_findings(writer: BatchWriter) -> dict[str, Any]:
    """Run the five predicates, write/refresh Findings, resolve the ones that no longer hold."""
    hits: list[Hit] = []
    by_kind: dict[str, int] = {}
    for kind, predicate in PREDICATES.items():
        found = predicate(writer)
        by_kind[kind] = len({h.key for h in found})
        hits.extend(found)
    existing = {
        str(r[0]): (str(r[1] or "open"), int(r[2] or 0))
        for r in writer.query("MATCH (f:Finding) RETURN f.key, f.state, f.reopened_count")
    }
    updates, resolved, transitions = plan_lifecycle(hits, existing, writer.observed_at)
    _write(writer, hits, updates, resolved)
    result: dict[str, Any] = {
        "by_kind": by_kind,
        "total": len(updates),
        "distinct_keps": len({h.kep_key for h in hits}),
        **transitions,
    }
    log.info("detect_findings_done", **result)
    return result
