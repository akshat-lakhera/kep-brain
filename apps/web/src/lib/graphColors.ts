/**
 * One colour per node label, used by every graph drawing. Values are the theme tokens in globals.css (the accent and
 * the categorical series, each stepped for light and dark), so the same label is the same hue on every page and in both
 * themes. Labels outside the list are drawn hollow in grey; the badge text and the legend name every node, so colour is
 * never the only cue.
 */
export interface NodePaint {
  fill: string;
  /** Hollow nodes draw a grey ring around a surface fill. */
  hollow?: boolean;
}

const PAINT: Record<string, NodePaint> = {
  KEP: { fill: "var(--c-accent)" },
  Person: { fill: "var(--c-series-1)" },
  SIG: { fill: "var(--c-series-2)" },
  WorkingGroup: { fill: "var(--c-series-2)" },
  Committee: { fill: "var(--c-series-2)" },
  Issue: { fill: "var(--c-series-3)" },
  PullRequest: { fill: "var(--c-series-4)" },
  Commit: { fill: "var(--c-series-5)" },
  Release: { fill: "var(--c-series-6)" },
  FeatureGate: { fill: "var(--c-series-6)" },
  Finding: { fill: "var(--c-series-7)" },
  Document: { fill: "var(--c-series-8)" },
  Section: { fill: "var(--c-series-8)" },
  Decision: { fill: "var(--c-text-secondary)" },
  StatusChange: { fill: "var(--c-text-secondary)" },
  Comment: { fill: "var(--c-text-secondary)" },
};

const OTHER: NodePaint = { fill: "var(--c-border-strong)", hollow: true };

export function paintFor(label: string): NodePaint {
  return PAINT[label] ?? OTHER;
}

/** The order labels appear in a legend: the ones with their own hue first, as listed above, then the rest. */
export function legendOrder(labels: Iterable<string>): string[] {
  const known = Object.keys(PAINT);
  return [...new Set(labels)].sort((a, b) => {
    const ia = known.indexOf(a);
    const ib = known.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}
