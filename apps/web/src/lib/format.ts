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
    "kep.yaml still says provisional or implementable, but the tracking issue is closed.",
  terminal_status_future_targets:
    "kep.yaml says withdrawn, rejected, deferred or replaced, but the KEP still targets a future release or is still tracked for one.",
  one_sided_replacement:
    "A KEP declares that it replaces another, but the replaced KEP does not list it as superseded-by.",
  stage_mismatch: "The stage in kep.yaml is not among the stage labels of the closed tracking issue.",
  milestone_mismatch: "The latest milestone in kep.yaml differs from the milestone of the tracking issue.",
};

/** Numeric KEP number from a path such as "keps/sig-node/1287-in-place-update". */
export function numberFromPath(path: string | null | undefined): number | null {
  if (!path) return null;
  const m = /\/(\d+)-[^/]*$/.exec(path);
  return m ? Number(m[1]) : null;
}
