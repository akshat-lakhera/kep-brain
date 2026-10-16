/** Relationship types in words, and the fixed order the evidence chain lists them in. */

/** [phrase when the node is the source, phrase when the node is the target]. */
const PHRASES: Record<string, [string, string]> = {
  OWNED_BY: ["owned by", "owns"],
  AUTHORED: ["authored", "authored by"],
  REVIEWS: ["reviews", "reviewed by"],
  APPROVES: ["approves", "approved by"],
  PRR_APPROVED: ["PRR approved", "PRR approved by"],
  EDITS: ["edits", "edited by"],
  DECIDED_BY: ["decided by", "decided"],
  ABOUT: ["about", "decisions and findings about this"],
  EVIDENCED_BY: ["evidence", "evidence for"],
  RECORDED_IN: ["recorded in", "records"],
  FROM_CHANGE: ["from change", "led to"],
  CHANGED: ["changed", "change of"],
  IN_PR: ["in PR", "contains"],
  IN_COMMIT: ["in commit", "commit of"],
  MERGED: ["merged", "merged by"],
  OPENED: ["opened", "opened by"],
  COMMENTED: ["commented", "commented by"],
  SUBMITTED: ["submitted", "submitted by"],
  ON: ["on", "has"],
  REPLIES_TO: ["replies to", "replied to by"],
  TRACKED_BY: ["tracked by", "tracks"],
  IMPLEMENTS: ["implements", "implemented by"],
  LABELED: ["labelled", "applied to"],
  MILESTONED: ["milestoned", "milestone of"],
  HAS_DOCUMENT: ["document", "document of"],
  HAS_SECTION: ["section", "section of"],
  PARENT_SECTION: ["under", "contains"],
  MENTIONS: ["mentions", "mentioned in"],
  GATED_BY: ["gated by", "gates"],
  ENABLED_IN: ["enabled in", "enables"],
  EXPOSES_METRIC: ["exposes metric", "metric of"],
  TARGETS: ["targets", "targeted by"],
  LATEST: ["latest", "latest for"],
  TO_RELEASE: ["to release", "release of"],
  REPLACES: ["replaces", "replaced by"],
  SUPERSEDED_BY: ["superseded by", "supersedes"],
  SEE_ALSO: ["see also", "see also"],
  RELATED_KEP: ["related", "related"],
  REFERENCES: ["references", "referenced by"],
  REFERS_TO: ["refers to", "referred to by"],
  CHAIRS: ["chairs", "chaired by"],
  TECH_LEAD: ["tech lead of", "tech lead"],
  EMERITUS_LEAD: ["emeritus lead of", "emeritus lead"],
  LIAISON: ["liaison for", "liaison"],
  STAKEHOLDER: ["stakeholder of", "stakeholder"],
  HAS_SUBPROJECT: ["subproject", "subproject of"],
  SUBPROJECT_LEAD: ["leads subproject", "led by"],
  APPROVER: ["approver in", "approvers"],
  REVIEWER: ["reviewer in", "reviewers"],
  EMERITUS_APPROVER: ["emeritus approver in", "emeritus approvers"],
  MEMBER_OF: ["member of", "members"],
  HAS_OWNERS: ["OWNERS file", "OWNERS of"],
  PARENT_OWNERS: ["parent OWNERS", "child OWNERS"],
  COMPONENT_DIR: ["component directory", "directory of"],
  APPLIES_LABEL: ["applies label", "applied by"],
  PARTICIPATES: ["participates in", "participating SIG"],
  COLLABORATED: ["collaborated with", "collaborated with"],
  CONTRIBUTED_TO: ["contributed to", "contributors"],
  ACTED: ["acted on", "acted by"],
  HAS_EVENT: ["event", "event of"],
  PRECEDES: ["precedes", "follows"],
  NEXT: ["next", "previous"],
  PREVIOUS: ["previous", "next"],
  REVERSES: ["reverses", "reversed by"],
  TOUCHED: ["touched", "touched by"],
  MODIFIES: ["modifies", "modified by"],
  AUTHORED_COMMIT: ["authored commit", "commit author"],
};

export type Dir = "out" | "in";

export function phraseFor(type: string, dir: Dir): string {
  const p = PHRASES[type];
  if (p) return dir === "out" ? p[0] : p[1];
  return type.toLowerCase().replace(/_/g, " ");
}

/** Section order of the chain: why, decided, evidence, owned, related, then everything else. */
export const RANKS = ["why it is designed this way", "decided by", "evidence", "owned by", "related", "other"] as const;

const DECIDED = new Set(["DECIDED_BY", "ABOUT", "APPROVES", "REVIEWS", "AUTHORED", "PRR_APPROVED", "EDITS", "FROM_CHANGE", "ACTED"]);
const EVIDENCE = new Set([
  "EVIDENCED_BY", "RECORDED_IN", "TRACKED_BY", "IMPLEMENTS", "CHANGED", "IN_PR", "IN_COMMIT", "ON", "COMMENTED", "SUBMITTED",
  "OPENED", "MERGED", "HAS_EVENT", "REPLIES_TO", "REFERENCES", "TOUCHED", "MODIFIES", "AUTHORED_COMMIT", "PREVIOUS", "REVERSES",
  "LABELED", "MILESTONED", "PRECEDES", "NEXT",
]); // prettier-ignore
const OWNED = new Set([
  "OWNED_BY", "PARTICIPATES", "CHAIRS", "TECH_LEAD", "EMERITUS_LEAD", "LIAISON", "APPROVER", "REVIEWER", "EMERITUS_APPROVER",
  "MEMBER_OF", "HAS_OWNERS", "PARENT_OWNERS", "COMPONENT_DIR", "HAS_SUBPROJECT", "SUBPROJECT_LEAD", "STAKEHOLDER", "APPLIES_LABEL",
  "COLLABORATED", "CONTRIBUTED_TO",
]); // prettier-ignore
const RELATED = new Set([
  "REPLACES", "SUPERSEDED_BY", "SEE_ALSO", "RELATED_KEP", "GATED_BY", "ENABLED_IN", "EXPOSES_METRIC", "TARGETS", "LATEST",
  "TO_RELEASE", "REFERS_TO", "HAS_DOCUMENT", "HAS_SECTION", "PARENT_SECTION", "MENTIONS",
]); // prettier-ignore

export function rankFor(type: string): number {
  if (DECIDED.has(type)) return 1;
  if (EVIDENCE.has(type)) return 2;
  if (OWNED.has(type)) return 3;
  if (RELATED.has(type)) return 4;
  return 5;
}

/** A node connected to a pull request or issue by one of these is shown inside that PR or issue block. */
export const CONTAINER_RELS = new Set(["ON", "IN_PR", "RECORDED_IN"]);
export const CONTAINER_LABELS = new Set(["PullRequest", "Issue"]);
