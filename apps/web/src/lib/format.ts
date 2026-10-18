/** "2026-10-17T18:40:00Z" -> "2026-10-17 18:40 UTC"; date-only strings pass through. */
export function isoUtc(value: string | null | undefined): string {
  if (!value) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const iso = d.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

export function isoDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().slice(0, 10);
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 7) : "";
}

/** Turn snake_case identifiers into sentence case words for headings. */
export function humanize(value: string): string {
  const s = value.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "s" unless the count is exactly one. */
export function pluralS(n: number): string {
  return n === 1 ? "" : "s";
}

/** A formatted count with its noun: "1 node", "12 nodes". */
export function plural(n: number, word: string): string {
  return `${n.toLocaleString("en-US")} ${word}${pluralS(n)}`;
}

/** A finite number, or null for anything else (strings, NaN, Infinity, missing). */
export function finiteNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** A fraction as a percentage; `trimZero` drops a trailing ".0". */
export function pct(v: number | null, trimZero = false): string {
  if (v === null) return "—";
  const text = `${(v * 100).toFixed(1)}%`;
  return trimZero ? text.replace(/\.0%$/, "%") : text;
}

/** Plain-language explanation of each finding kind (03 §7.5). */
export const FINDING_KIND_TEXT: Record<string, string> = {
  active_status_closed_issue:
    "kep.yaml says provisional or implementable while the tracking issue is closed. Usually the feature shipped and status was never set to implemented; when a lifecycle bot closed the issue, the status may be right.",
  terminal_status_future_targets:
    "kep.yaml says withdrawn, rejected, deferred or replaced, but the KEP still targets a future release or is still tracked for one.",
  one_sided_replacement:
    "A KEP declares that it replaces another, but the replaced KEP does not list it as superseded-by.",
  stage_mismatch: "The stage in kep.yaml is not among the stage labels of the closed tracking issue.",
  milestone_mismatch: "The latest milestone in kep.yaml differs from the milestone of the tracking issue.",
};

/** Plain-language label for a finding's suggested_fix key; unknown keys fall back to humanize(). */
export const SUGGESTED_FIX_TEXT: Record<string, string> = {
  set_status_implemented: "Set status to implemented",
  set_status_withdrawn_or_deferred: "Set status to withdrawn or deferred",
  update_stage: "Update the stage",
  update_latest_milestone: "Update latest-milestone",
  add_superseded_by: "Add superseded-by on the replaced KEP",
  remove_future_milestones: "Remove the future milestones",
  review_status: "Review the status",
  none_historical_label: "No change: the label is historical",
  in_flight_wait_for_freeze: "In flight: expect the kep.yaml PR at enhancements freeze",
};

export function fixLabel(key: string): string {
  return SUGGESTED_FIX_TEXT[key] ?? humanize(key);
}

/** Plain-language phrase for each abstain reason code the API may return. */
export const ABSTAIN_REASON_TEXT: Record<string, string> = {
  no_evidence: "the graph holds nothing relevant to the question",
  out_of_scope: "the question is not about KEPs, SIGs or people in this graph, nor about KEP Brain itself",
  unsupported_claims: "the draft answer cited a record that was not returned, or cited none",
  budget_exhausted: "the answering budget ran out before an answer was checked",
  graph_unavailable: "the graph database did not answer",
};

/**
 * Markdown link, code and emphasis syntax reduced to its text, for one-line summaries shown as plain text:
 * "[CronJob](https://…)" -> "CronJob", "`x`" -> "x", "**bold**" -> "bold", "_em_" -> "em".
 */
export function stripMarkdown(s: string): string {
  return s
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, "$2")
    .replace(/(^|[\s(])[*_](?=\S)([^*_\n]*?\S)[*_](?=[\s).,;:!?]|$)/g, "$1$2")
    .replace(/[ \t]*\n[ \t]*/g, " ");
}

/** Numeric KEP number from a path such as "keps/sig-node/1287-in-place-update". */
export function numberFromPath(path: string | null | undefined): number | null {
  if (!path) return null;
  const m = /\/(\d+)-[^/]*$/.exec(path);
  return m ? Number(m[1]) : null;
}

/**
 * The kep.yaml file of a KEP on GitHub. The API's source_url may name the KEP folder ("…/tree/<sha>/keps/…/268-x");
 * the file itself is "…/blob/<sha>/keps/…/268-x/kep.yaml". A URL that already names a file is returned unchanged.
 */
export function kepYamlUrl(sourceUrl: string | null | undefined): string | null {
  if (!sourceUrl) return null;
  const m = /^(https:\/\/github\.com\/[^/]+\/[^/]+)\/(?:tree|blob)\/([^/]+)\/(.+?)\/?$/.exec(sourceUrl);
  if (!m) return sourceUrl;
  const [, repo, ref, path] = m;
  if (/\.ya?ml$/.test(path)) return `${repo}/blob/${ref}/${path}`;
  return `${repo}/blob/${ref}/${path}/kep.yaml`;
}
