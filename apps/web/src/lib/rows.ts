/** Rows-per-page settings shared by server pages and the client control. */
export const ROWS_PRESETS = [10, 25, 50, 100] as const;
export const ROWS_DEFAULT = 10;
export const ROWS_MAX = 10_000;

/** Parse `?rows=`: a preset or custom positive integer, `all`, or the default. */
export function parseRows(raw: string | string[] | undefined): number | "all" {
  const v = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  if (v === "all") return "all";
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? Math.min(n, ROWS_MAX) : ROWS_DEFAULT;
}
