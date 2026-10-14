"""Deterministic `Decision` derivation (03 §8.2).

Six derived kinds, each built only from records already in the graph:

| kind | trigger |
|---|---|
| `status_transition` | metadata `StatusChange` on `status` (not to a terminal value) |
| `withdrawal` | metadata `StatusChange` on `status` to `withdrawn`/`rejected`/`deferred` |
| `stage_graduation` | `stage` moved to a higher stage, or a `milestone.<stage>` first recorded |
| `milestone_retarget` | `latest_milestone` or `milestone.<stage>` moved to a later release |
| `prr_approval` | a `PRR_APPROVED {stage}` edge (stage approver in the PRR file) |
| `replacement` | a `REPLACES` edge |

Deciders (`DECIDED_BY {role}`) come from the PR that merged the change: `approver` (review APPROVED
before the merge), `approve_command`/`lgtm` (Prow commands on their own line in a review or comment),
`merger`, `author`; without a PR the commit's resolvable author (`author`). Summaries use fixed templates.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.db.batch import BatchWriter
from app.ingest.common import is_bot, iso

log = structlog.get_logger(__name__)

TERMINAL = {"withdrawn", "rejected", "deferred"}
STAGE_RANK = {"alpha": 1, "beta": 2, "stable": 3, "deprecated": 4, "disabled": 5, "removed": 6}
ROLE_ORDER = ("approver", "approve_command", "lgtm", "prr_approver", "author", "merger", "actor")
_SHA_IN_URL = re.compile(r"/blob/([0-9a-f]{40})/")
_RELEASE = re.compile(r"^v1\.(\d+)$")
REPO = "kubernetes/enhancements"


def release_minor(value: str | None) -> int | None:
    m = _RELEASE.match(value or "")
    return int(m.group(1)) if m else None


def kep_ref(number: int | None, key: str) -> str:
    return f"KEP-{number}" if number is not None else key


# -- input rows -------------------------------------------------------------------


@dataclass
class ChangeRow:
    kep_key: str
    kep_number: int | None
    sc_key: str
    field: str
    from_value: str | None
    to_value: str | None
    at: int
    is_reversal: bool
    sc_url: str | None
    previous_key: str | None = None
    commit_key: str | None = None
    commit_sha: str | None = None
    commit_url: str | None = None
    commit_at: int | None = None
    commit_author: str | None = None
    pr_key: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    pr_merged_at: int | None = None
    pr_merged_by: str | None = None
    pr_author: str | None = None


@dataclass
class PrActivity:
    """Reviews and command comments on one PR."""

    reviews: list[dict[str, Any]] = field(default_factory=list)  # key, state, author_login, submitted_at, commands, url
    comments: list[dict[str, Any]] = field(default_factory=list)  # key, author_login, created_at, commands, url


@dataclass
class DecisionPlan:
    key: str
    kind: str
    kep_key: str
    summary: str
    decided_at: int
    url: str
    deciders: list[tuple[str, str, int]]  # (login, role, at)
    evidence: list[tuple[str, str, str, str]]  # (label, key, evidence_kind, source_url)
    from_value: str | None = None
    to_value: str | None = None
    stage: str | None = None
    from_change: str | None = None
    reverses_change: str | None = None  # StatusChange key whose decision this one reverses
    human_decider: bool = True

    def row(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "kep_path": self.kep_key,
            "summary": self.summary,
            "decided_at": self.decided_at,
            "decided_at_iso": iso(self.decided_at),
            "derived": True,
            "human_decider": self.human_decider,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "stage": self.stage,
            "url": self.url,
            "source_url": self.url,
            "source_repo": REPO,
        }


# -- classification -----------------------------------------------------------------


def classify(change: ChangeRow) -> tuple[str, str | None] | None:
    """Decision kind (and stage) for a metadata change, or None when it is not a decision."""
    f, old, new = change.field, change.from_value, change.to_value
    if f == "status":
        if not new or new == old:
            return None
        return ("withdrawal" if new in TERMINAL else "status_transition", None)
    if f == "stage":
        if not new or new not in STAGE_RANK:
            return None
        if old is None or STAGE_RANK.get(old, 0) < STAGE_RANK[new]:
            return ("stage_graduation", new)
        return None
    if f == "latest_milestone" or f.startswith("milestone."):
        stage = f.split(".", 1)[1] if f.startswith("milestone.") else None
        new_minor, old_minor = release_minor(new), release_minor(old)
        if new_minor is None:
            return None
        if old is None and stage is not None:
            return ("stage_graduation", stage)
        if old_minor is not None and new_minor > old_minor:
            return ("milestone_retarget", stage)
    return None


def pr_deciders(change: ChangeRow, activity: PrActivity | None) -> list[tuple[str, str, int]]:
    """(login, role, at) for the PR behind a change; reviews/commands after the merge are ignored."""
    out: list[tuple[str, str, int]] = []
    cutoff = change.pr_merged_at
    if change.pr_key and activity:
        for rv in activity.reviews:
            login, at = rv.get("author_login"), rv.get("submitted_at")
            if not login or at is None or (cutoff is not None and at > cutoff):
                continue
            if rv.get("state") == "APPROVED":
                out.append((login, "approver", at))
            out.extend(_command_roles(login, rv.get("commands") or [], at))
        for cm in activity.comments:
            login, at = cm.get("author_login"), cm.get("created_at")
            if not login or at is None or (cutoff is not None and at > cutoff):
                continue
            out.extend(_command_roles(login, cm.get("commands") or [], at))
    if change.pr_key:
        if change.pr_merged_by and change.pr_merged_at:
            out.append((change.pr_merged_by, "merger", change.pr_merged_at))
        if change.pr_author:
            out.append((change.pr_author, "author", change.commit_at or change.at))
    elif change.commit_author:
        out.append((change.commit_author, "author", change.commit_at or change.at))
    return _dedupe(out)


def _command_roles(login: str, commands: Sequence[str], at: int) -> list[tuple[str, str, int]]:
    roles = []
    if "/approve" in commands:
        roles.append((login, "approve_command", at))
    if "/lgtm" in commands:
        roles.append((login, "lgtm", at))
    return roles


def _dedupe(items: Sequence[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """One edge per (login, role); keep the latest time (the approval that counted at merge)."""
    best: dict[tuple[str, str], int] = {}
    for login, role, at in items:
        k = (login, role)
        best[k] = max(best.get(k, at), at)
    return sorted(((lg, rl, at) for (lg, rl), at in best.items()), key=lambda x: (ROLE_ORDER.index(x[1]), x[0]))


def _approver_names(deciders: Sequence[tuple[str, str, int]]) -> list[str]:
    names: list[str] = []
    for login, role, _ in deciders:
        if role in ("approver", "approve_command") and not is_bot(login) and login not in names:
            names.append(login)
    return names


def _tail(change: ChangeRow, deciders: Sequence[tuple[str, str, int]], decided_at: int) -> str:
    parts = []
    if change.pr_number is not None:
        parts.append(f" in PR #{change.pr_number}")
    elif change.commit_sha:
        parts.append(f" in commit {change.commit_sha[:10]}")
    approvers = _approver_names(deciders)
    if approvers:
        parts.append(f", approved by {', '.join(approvers)}")
    mergers = [lg for lg, rl, _ in deciders if rl == "merger"]
    if mergers:
        who = "automation (" + mergers[0] + ")" if is_bot(mergers[0]) else mergers[0]
        parts.append(f"; merged by {who} on {iso(decided_at)[:10]}")
    else:
        parts.append(f" on {iso(decided_at)[:10]}")
    return "".join(parts) + "."


def summarise(
    kind: str, change: ChangeRow, stage: str | None, deciders: Sequence[tuple[str, str, int]], at: int
) -> str:
    ref = kep_ref(change.kep_number, change.kep_key)
    old, new = change.from_value, change.to_value
    tail = _tail(change, deciders, at)
    if kind == "status_transition":
        head = f"{ref} status changed from {old} to {new}" if old else f"{ref} status set to {new}"
    elif kind == "withdrawal":
        head = f"{ref} was marked {new}" + (f" (previously {old})" if old else "")
    elif kind == "stage_graduation":
        if change.field == "stage":
            head = f"{ref} graduated to {new}" + (f" from {old}" if old else "")
        else:
            head = f"{ref} set milestone.{stage} to {new}"
    else:
        what = "latest-milestone" if change.field == "latest_milestone" else change.field
        head = f"{ref} {what} moved from {old} to {new}"
    return head + tail


def _before_merge(at: int | None, merged_at: int | None) -> bool:
    return merged_at is None or (at or 0) <= merged_at


def plan_change_decision(change: ChangeRow, activity: PrActivity | None, bots: set[str]) -> DecisionPlan | None:
    cls = classify(change)
    if cls is None:
        return None
    kind, stage = cls
    deciders = pr_deciders(change, activity)
    decided_at = change.pr_merged_at or change.commit_at or change.at
    disc = change.commit_sha or change.sc_key
    key = (
        f"dec:{kind}:{change.kep_key}:{disc}"
        if change.field == "status"
        else f"dec:{kind}:{change.kep_key}:{change.field}:{disc}"
    )
    evidence: list[tuple[str, str, str, str]] = []
    if change.pr_key and change.pr_url:
        evidence.append(("PullRequest", change.pr_key, "pr", change.pr_url))
        if activity:
            names = {d[0] for d in deciders}
            for rv in activity.reviews:
                relevant = rv.get("author_login") in names and (rv.get("state") == "APPROVED" or rv.get("commands"))
                if relevant and _before_merge(rv.get("submitted_at"), change.pr_merged_at):
                    evidence.append(("Review", rv["key"], "review", rv.get("url") or change.pr_url))
            for cm in activity.comments:
                cmds = cm.get("commands") or []
                relevant = cm.get("author_login") in names and ("/approve" in cmds or "/lgtm" in cmds)
                if relevant and _before_merge(cm.get("created_at"), change.pr_merged_at):
                    evidence.append(("Comment", cm["key"], "command_comment", cm.get("url") or change.pr_url))
    if change.commit_key and change.commit_url:
        evidence.append(("Commit", change.commit_key, "commit", change.commit_url))
    evidence.append(("StatusChange", change.sc_key, "status_change", change.sc_url or change.commit_url or ""))
    url = change.pr_url or change.commit_url or change.sc_url or ""
    return DecisionPlan(
        key=key,
        kind=kind,
        kep_key=change.kep_key,
        summary=summarise(kind, change, stage, deciders, decided_at),
        decided_at=decided_at,
        url=url,
        deciders=deciders,
        evidence=evidence,
        from_value=change.from_value,
        to_value=change.to_value,
        stage=stage,
        from_change=change.sc_key,
        reverses_change=change.previous_key if change.is_reversal else None,
        human_decider=any(lg not in bots and not is_bot(lg) for lg, _, _ in deciders),
    )


# -- graph reads ------------------------------------------------------------------------

_CHANGES_Q = """
MATCH (k:KEP)-[:CHANGED]->(sc:StatusChange {kind: 'metadata'})
WHERE sc.field IN ['status', 'stage', 'latest_milestone'] OR sc.field STARTS WITH 'milestone.'
OPTIONAL MATCH (sc)-[:IN_COMMIT]->(c:Commit)
OPTIONAL MATCH (c)-[:IN_PR]->(p:PullRequest)
OPTIONAL MATCH (sc)-[:PREVIOUS]->(prev:StatusChange)
RETURN k.key, k.number, sc.key, sc.field, sc.from_value, sc.to_value, sc.at, sc.is_reversal, sc.source_url,
       prev.key, c.key, c.sha, c.url, c.authored_at, c.author_login,
       p.key, p.number, p.url, p.merged_at, p.merged_by_login, p.author_login
"""

_REVIEWS_Q = """
MATCH (r:Review)-[:ON]->(p:PullRequest) WHERE p.key IN $prs
RETURN p.key, r.key, r.state, r.author_login, r.submitted_at, r.commands, r.url
"""

_COMMENTS_Q = """
MATCH (c:Comment)-[:ON]->(p:PullRequest) WHERE p.key IN $prs
RETURN p.key, c.key, c.author_login, c.created_at, c.commands, c.url
"""


def load_changes(writer: BatchWriter) -> list[ChangeRow]:
    out = []
    for r in writer.query(_CHANGES_Q):
        out.append(
            ChangeRow(
                kep_key=r[0], kep_number=r[1], sc_key=r[2], field=r[3], from_value=r[4], to_value=r[5],
                at=int(r[6] or 0), is_reversal=bool(r[7]), sc_url=r[8], previous_key=r[9],
                commit_key=r[10], commit_sha=r[11], commit_url=r[12], commit_at=r[13], commit_author=r[14],
                pr_key=r[15], pr_number=r[16], pr_url=r[17], pr_merged_at=r[18], pr_merged_by=r[19], pr_author=r[20],
            )
        )  # fmt: skip
    return out


def load_activity(writer: BatchWriter, pr_keys: Sequence[str]) -> dict[str, PrActivity]:
    acts: dict[str, PrActivity] = defaultdict(PrActivity)
    keys = sorted(set(pr_keys))
    for i in range(0, len(keys), 500):
        chunk = keys[i : i + 500]
        for p, key, state, login, at, cmds, url in writer.query(_REVIEWS_Q, {"prs": chunk}):
            acts[p].reviews.append(
                {
                    "key": key,
                    "state": state,
                    "author_login": login,
                    "submitted_at": at,
                    "commands": cmds or [],
                    "url": url,
                }
            )
        for p, key, login, at, cmds, url in writer.query(_COMMENTS_Q, {"prs": chunk}):
            acts[p].comments.append(
                {"key": key, "author_login": login, "created_at": at, "commands": cmds or [], "url": url}
            )
    return acts


def load_bots(writer: BatchWriter) -> set[str]:
    return {str(r[0]) for r in writer.query("MATCH (p:Person) WHERE p.is_bot = true RETURN p.key")}


def _commit_from_url(url: str | None) -> str | None:
    m = _SHA_IN_URL.search(url or "")
    return f"{REPO}@{m.group(1)}" if m else None


def plan_prr_decisions(writer: BatchWriter, bots: set[str]) -> list[DecisionPlan]:
    rows = writer.query(
        "MATCH (a:Person)-[e:PRR_APPROVED]->(k:KEP) "
        "OPTIONAL MATCH (k)-[:HAS_DOCUMENT]->(d:Document {kind: 'prr'}) "
        "RETURN k.key, k.number, a.key, e.stage, e.valid_from, e.source_url, d.key, d.url"
    )
    grouped: dict[tuple[str, str], list[list[Any]]] = defaultdict(list)
    for r in rows:
        if r[3]:
            grouped[(str(r[0]), str(r[3]))].append(r)
    commit_keys = {ck for rs in grouped.values() for r in rs if (ck := _commit_from_url(r[5]))}
    commits = _commit_info(writer, commit_keys)
    plans = []
    for (kep_key, stage), rs in sorted(grouped.items()):
        rs.sort(key=lambda r: int(r[4] or 0))
        first = rs[0]
        at = int(first[4] or 0)
        number = first[1]
        logins = sorted({str(r[2]) for r in rs})
        evidence: list[tuple[str, str, str, str]] = []
        if first[6]:
            evidence.append(("Document", str(first[6]), "prr_file", str(first[7] or first[5] or "")))
        ckey = _commit_from_url(first[5])
        info = commits.get(ckey or "")
        if info:
            evidence.append(("Commit", ckey or "", "commit", info["url"]))
            if info.get("pr_key"):
                evidence.append(("PullRequest", info["pr_key"], "pr", info["pr_url"]))
        url = (info or {}).get("pr_url") or str(first[7] or first[5] or "")
        if not evidence and not url:
            continue
        plans.append(
            DecisionPlan(
                key=f"dec:prr_approval:{kep_key}:{stage}",
                kind="prr_approval",
                kep_key=kep_key,
                summary=(
                    f"{', '.join(logins)} gave the production readiness approval for "
                    f"{kep_ref(number, kep_key)} at {stage} on {iso(at)[:10]}."
                ),
                decided_at=at,
                url=url,
                deciders=[(lg, "prr_approver", at) for lg in logins],
                evidence=evidence,
                stage=stage,
                human_decider=any(lg not in bots and not is_bot(lg) for lg in logins),
            )
        )
    return plans


def _commit_info(writer: BatchWriter, keys: set[str]) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    rows = writer.query(
        "MATCH (c:Commit) WHERE c.key IN $keys OPTIONAL MATCH (c)-[:IN_PR]->(p:PullRequest) "
        "RETURN c.key, c.url, p.key, p.url",
        {"keys": sorted(keys)},
    )
    return {str(r[0]): {"url": r[1], "pr_key": r[2], "pr_url": r[3]} for r in rows}


def plan_replacement_decisions(writer: BatchWriter, bots: set[str]) -> list[DecisionPlan]:
    rows = writer.query(
        "MATCH (s:KEP)-[r:REPLACES]->(p:KEP) "
        "OPTIONAL MATCH (s)-[:HAS_DOCUMENT]->(d:Document {kind: 'kep_yaml'}) "
        "RETURN s.key, s.number, p.key, p.number, r.valid_from, r.source_url, d.key, d.url"
    )
    pairs: dict[tuple[str, str], list[Any]] = {}
    for r in rows:  # earliest interval per pair: when the replacement was declared
        k = (str(r[0]), str(r[2]))
        if k not in pairs or int(r[4] or 0) < int(pairs[k][4] or 0):
            pairs[k] = r
    commits = _commit_info(writer, {ck for r in pairs.values() if (ck := _commit_from_url(r[5]))})
    plans = []
    for (succ, pred), r in sorted(pairs.items()):
        at = int(r[4] or 0)
        approvers = [
            str(a[0])
            for a in writer.query(
                "MATCH (a:Person)-[e:APPROVES]->(s:KEP {key: $s}) WHERE e.valid_from <= $t AND e.valid_to > $t "
                "RETURN DISTINCT a.key ORDER BY a.key",
                {"s": succ, "t": at},
            )
        ]
        evidence: list[tuple[str, str, str, str]] = []
        if r[6]:
            evidence.append(("Document", str(r[6]), "kep_yaml", str(r[5] or r[7] or "")))
        ckey = _commit_from_url(r[5])
        info = commits.get(ckey or "")
        if info:
            evidence.append(("Commit", ckey or "", "commit", info["url"]))
            if info.get("pr_key"):
                evidence.append(("PullRequest", info["pr_key"], "pr", info["pr_url"]))
        url = (info or {}).get("pr_url") or str(r[5] or r[7] or "")
        tail = f", approved by {', '.join(approvers)}" if approvers else ""
        plans.append(
            DecisionPlan(
                key=f"dec:replacement:{succ}:{pred}",
                kind="replacement",
                kep_key=succ,
                summary=(
                    f"{kep_ref(r[1], succ)} declared that it replaces {kep_ref(r[3], pred)} on {iso(at)[:10]}{tail}."
                ),
                decided_at=at,
                url=url,
                deciders=[(a, "approver", at) for a in approvers],
                evidence=evidence,
                to_value=pred,
                human_decider=any(a not in bots and not is_bot(a) for a in approvers),
            )
        )
    return plans


# -- writes -------------------------------------------------------------------------------


def write_decisions(writer: BatchWriter, plans: Sequence[DecisionPlan]) -> None:
    if not plans:
        return
    writer.upsert_nodes("Decision", [p.row() for p in plans])
    about = [{"from": p.key, "to": p.kep_key, "props": {"w": 1}} for p in plans]
    writer.upsert_edges("ABOUT", "Decision", "KEP", about)
    decided = [
        {"from": p.key, "to": lg, "props": {"role": role, "at": at, "at_iso": iso(at), "source_url": p.url,
                                             "w": 50 if is_bot(lg) else 1}}
        for p in plans
        for lg, role, at in p.deciders
    ]  # fmt: skip
    writer.upsert_edges("DECIDED_BY", "Decision", "Person", decided, identity=["role"])
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in plans:
        for label, key, kind, url in p.evidence:
            by_label[label].append(
                {"from": p.key, "to": key, "props": {"evidence_kind": kind, "source_url": url, "w": 1}}
            )
    for label, rows in by_label.items():
        writer.upsert_edges("EVIDENCED_BY", "Decision", label, rows, identity=["evidence_kind"])
    from_change = [{"from": p.key, "to": p.from_change, "props": {}} for p in plans if p.from_change]
    writer.upsert_edges("FROM_CHANGE", "Decision", "StatusChange", from_change)
    by_change = {p.from_change: p.key for p in plans if p.from_change}
    reverses = [
        {"from": p.key, "to": by_change[p.reverses_change], "props": {}}
        for p in plans
        if p.reverses_change and p.reverses_change in by_change
    ]
    writer.upsert_edges("REVERSES", "Decision", "Decision", reverses)


def derive_decisions(writer: BatchWriter) -> dict[str, int]:
    """Derive every deterministic Decision from the current graph; idempotent (keys are deterministic)."""
    bots = load_bots(writer)
    changes = load_changes(writer)
    activity = load_activity(writer, [c.pr_key for c in changes if c.pr_key])
    plans: list[DecisionPlan] = []
    for ch in changes:
        plan = plan_change_decision(ch, activity.get(ch.pr_key or ""), bots)
        if plan is not None:
            plans.append(plan)
    plans.extend(plan_prr_decisions(writer, bots))
    plans.extend(plan_replacement_decisions(writer, bots))
    # Same key from two changes (one commit touching a field twice cannot happen; guard anyway).
    unique: dict[str, DecisionPlan] = {}
    for p in plans:
        unique.setdefault(p.key, p)
    write_decisions(writer, list(unique.values()))
    counts: dict[str, int] = defaultdict(int)
    for p in unique.values():
        counts[p.kind] += 1
    counts["total"] = len(unique)
    counts["with_pr"] = sum(1 for p in unique.values() if any(e[2] == "pr" for e in p.evidence))
    log.info("derive_decisions_done", **counts)
    return dict(counts)
