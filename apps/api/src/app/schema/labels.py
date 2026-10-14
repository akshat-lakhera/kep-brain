"""Allow-lists of node labels and relationship types (03 §4, §5).

Only names in these sets are ever interpolated into Cypher.
"""

from __future__ import annotations

# Sentinel for an open validity interval: 2100-01-01T00:00:00Z (03 P5).
VALID_TO_OPEN = 4102444800

NODE_LABELS: frozenset[str] = frozenset(
    {
        "SIG", "WorkingGroup", "Committee", "Subproject", "Person", "Alias", "Document", "Section",
        "KEP", "FeatureGate", "Component", "Metric", "Release", "Label", "ExternalRef", "Commit",
        "PullRequest", "Issue", "Review", "Comment", "StatusChange", "Decision", "Finding",
        "Ticket", "OwnersFile", "AnswerCache",
    }
)  # fmt: skip

STATE_RELS: frozenset[str] = frozenset(
    {
        "CHAIRS", "TECH_LEAD", "EMERITUS_LEAD", "LIAISON", "STAKEHOLDER", "SUBPROJECT_LEAD",
        "APPROVER", "REVIEWER", "EMERITUS_APPROVER", "MEMBER_OF", "APPLIES_LABEL", "COMPONENT_DIR",
        "OWNED_BY", "PARTICIPATES", "AUTHORED", "REVIEWS", "APPROVES", "EDITS", "PRR_APPROVED",
        "REPLACES", "SUPERSEDED_BY", "SEE_ALSO", "REFERS_TO", "GATED_BY", "ENABLED_IN",
        "EXPOSES_METRIC", "TARGETS", "LATEST", "TRACKED_BY", "LABELED", "MILESTONED",
    }
)  # fmt: skip

OTHER_RELS: frozenset[str] = frozenset(
    {
        "HAS_SUBPROJECT", "HAS_OWNERS", "PARENT_OWNERS", "HAS_DOCUMENT", "HAS_SECTION", "NEXT",
        "PARENT_SECTION", "MENTIONS", "TOUCHED", "MODIFIES", "PRECEDES", "CHANGED", "HAS_EVENT",
        "IN_COMMIT", "PREVIOUS", "TO_RELEASE", "ACTED", "IN_PR", "AUTHORED_COMMIT", "ABOUT",
        "DECIDED_BY", "EVIDENCED_BY", "FROM_CHANGE", "REVERSES", "RECORDED_IN", "OPENED", "MERGED",
        "COMMENTED", "SUBMITTED", "ON", "REPLIES_TO", "REFERENCES", "IMPLEMENTS",
        "COLLABORATED", "CONTRIBUTED_TO", "RELATED_KEP",
    }
)  # fmt: skip

REL_TYPES: frozenset[str] = STATE_RELS | OTHER_RELS

KEP_STATUSES = ("provisional", "implementable", "implemented", "deferred", "rejected", "withdrawn", "replaced")
KEP_STAGES = ("alpha", "beta", "stable", "deprecated", "disabled", "removed")
FINDING_KINDS = (
    "active_status_closed_issue",
    "terminal_status_future_targets",
    "one_sided_replacement",
    "stage_mismatch",
    "milestone_mismatch",
)
BOT_LOGINS = frozenset({"k8s-ci-robot", "k8s-triage-robot", "fejta-bot", "k8s-merge-robot", "dependabot"})
