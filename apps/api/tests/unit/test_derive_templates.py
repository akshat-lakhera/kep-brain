"""Decision classification, deciders and fixed summary templates (03 §8.2)."""

from __future__ import annotations

from app.ingest.derive import ChangeRow, PrActivity, classify, plan_change_decision

MERGED = 1768531528  # 2026-01-16T02:45:28Z
KEP = "keps/sig-node/1287-in-place-update-pod-resources"
SHA = "d47a8df46c8c26d6300fd30047520e397127805c"


def _change(**kw: object) -> ChangeRow:
    base: dict[str, object] = {
        "kep_key": KEP,
        "kep_number": 1287,
        "sc_key": f"sc:{KEP}:status:{SHA}",
        "field": "status",
        "from_value": "implementable",
        "to_value": "implemented",
        "at": 1767035207,
        "is_reversal": False,
        "sc_url": f"https://github.com/kubernetes/enhancements/blob/{SHA}/{KEP}/kep.yaml",
        "commit_key": f"kubernetes/enhancements@{SHA}",
        "commit_sha": SHA,
        "commit_url": f"https://github.com/kubernetes/enhancements/commit/{SHA}",
        "commit_at": 1767035207,
        "pr_key": "kubernetes/enhancements#5761",
        "pr_number": 5761,
        "pr_url": "https://github.com/kubernetes/enhancements/pull/5761",
        "pr_merged_at": MERGED,
        "pr_merged_by": "k8s-ci-robot",
        "pr_author": "natasha41575",
    }
    base.update(kw)
    return ChangeRow(**base)  # type: ignore[arg-type]


ACTIVITY = PrActivity(
    reviews=[
        {"key": "r1", "state": "APPROVED", "author_login": "sergeykanzhelev", "submitted_at": MERGED - 300000,
         "commands": ["/lgtm", "/approve"], "url": "https://github.com/kubernetes/enhancements/pull/5761#pullrequestreview-1"},
        {"key": "r2", "state": "APPROVED", "author_login": "mrunalp", "submitted_at": MERGED - 360,
         "commands": [], "url": "https://github.com/kubernetes/enhancements/pull/5761#pullrequestreview-2"},
        {"key": "r3", "state": "APPROVED", "author_login": "late", "submitted_at": MERGED + 10,
         "commands": [], "url": "u"},
    ],
    comments=[
        {"key": "c1", "author_login": "tallclair", "created_at": MERGED - 800000, "commands": ["/lgtm"], "url": "c"},
        {"key": "c2", "author_login": "lmktfy", "created_at": MERGED - 900000, "commands": [], "url": "c"},
    ],
)  # fmt: skip


def test_dec01_status_transition_with_pr_approvers() -> None:
    plan = plan_change_decision(_change(), ACTIVITY, {"k8s-ci-robot"})
    assert plan is not None
    assert plan.key == f"dec:status_transition:{KEP}:{SHA}"
    assert plan.decided_at == MERGED
    roles = {(lg, rl) for lg, rl, _ in plan.deciders}
    assert ("sergeykanzhelev", "approver") in roles
    assert ("sergeykanzhelev", "approve_command") in roles
    assert ("sergeykanzhelev", "lgtm") in roles
    assert ("mrunalp", "approver") in roles
    assert ("tallclair", "lgtm") in roles
    assert ("k8s-ci-robot", "merger") in roles
    assert ("natasha41575", "author") in roles
    assert not any(lg == "late" for lg, _, _ in plan.deciders)
    assert plan.human_decider is True
    assert plan.summary == (
        "KEP-1287 status changed from implementable to implemented in PR #5761, "
        "approved by mrunalp, sergeykanzhelev; merged by automation (k8s-ci-robot) on 2026-01-16."
    )
    kinds = [e[2] for e in plan.evidence]
    assert kinds.count("review") == 2 and "command_comment" in kinds
    assert {"pr", "commit", "status_change"} <= set(kinds)
    assert plan.url.endswith("/pull/5761")


def test_withdrawal_and_without_pr() -> None:
    change = _change(to_value="withdrawn", pr_key=None, pr_number=None, pr_url=None, pr_merged_at=None,
                     pr_merged_by=None, pr_author=None, commit_author="alice")  # fmt: skip
    plan = plan_change_decision(change, None, set())
    assert plan is not None and plan.kind == "withdrawal"
    assert plan.deciders == [("alice", "author", change.commit_at)]
    assert plan.summary.startswith("KEP-1287 was marked withdrawn (previously implementable) in commit d47a8df46c")
    assert plan.url == change.commit_url


def test_only_bot_deciders_is_not_human() -> None:
    change = _change(pr_author="k8s-ci-robot")
    plan = plan_change_decision(change, PrActivity(), {"k8s-ci-robot"})
    assert plan is not None and plan.human_decider is False


def test_classify_stage_and_milestones() -> None:
    assert classify(_change(field="stage", from_value="alpha", to_value="beta")) == ("stage_graduation", "beta")
    assert classify(_change(field="stage", from_value="stable", to_value="beta")) is None
    assert classify(_change(field="stage", from_value=None, to_value="alpha")) == ("stage_graduation", "alpha")
    assert classify(_change(field="milestone.beta", from_value=None, to_value="v1.31")) == ("stage_graduation", "beta")
    assert classify(_change(field="milestone.beta", from_value="v1.30", to_value="v1.31")) == (
        "milestone_retarget",
        "beta",
    )
    assert classify(_change(field="latest_milestone", from_value="v1.36", to_value="v1.37")) == (
        "milestone_retarget",
        None,
    )
    assert classify(_change(field="latest_milestone", from_value="v1.37", to_value="v1.36")) is None
    assert classify(_change(field="status", from_value="implemented", to_value="implemented")) is None


def test_stage_key_includes_field_and_reversal_link() -> None:
    change = _change(field="stage", from_value="beta", to_value="stable", is_reversal=True, previous_key="sc:prev")
    plan = plan_change_decision(change, ACTIVITY, set())
    assert plan is not None
    assert plan.key == f"dec:stage_graduation:{KEP}:stage:{SHA}"
    assert plan.reverses_change == "sc:prev"
    assert plan.summary.startswith("KEP-1287 graduated to stable from beta in PR #5761")
