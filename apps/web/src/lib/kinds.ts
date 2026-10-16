import { humanize } from "./format";

/** Series slots (--c-series-N) available for finding kinds; further kinds are drawn grey. */
const SLOTS = 5;

/** Kinds in a stable (alphabetical) order, so a kind keeps its colour whatever the counts or filters are. */
export function kindTones(kinds: string[]): Map<string, number | null> {
  return new Map([...kinds].sort().map((k, i) => [k, i < SLOTS ? i + 1 : null]));
}

export function toneColor(tone: number | null | undefined): string {
  return tone ? `var(--c-series-${tone})` : "var(--c-border-strong)";
}

/** Plain-words label of a finding kind; the snake_case identifier stays the key and the URL value. */
export const kindLabel = humanize;
