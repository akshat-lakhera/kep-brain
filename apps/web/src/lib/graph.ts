import type { GraphNode } from "./api/types";
import { numberFromPath } from "./format";

/** Node label -> Cytoscape shape (05 §7.4). Any other label uses "rectangle". */
const SHAPES: Record<string, string> = {
  KEP: "round-rectangle",
  Person: "ellipse",
  SIG: "hexagon",
  WorkingGroup: "hexagon",
  Committee: "hexagon",
  PullRequest: "diamond",
  Issue: "triangle",
  Commit: "round-diamond",
  Review: "round-triangle",
  Comment: "round-tag",
  Release: "tag",
  StatusChange: "pentagon",
  Decision: "octagon",
  Document: "cut-rectangle",
  Section: "bottom-round-rectangle",
  FeatureGate: "rhomboid",
  Finding: "concave-hexagon",
};

export function shapeFor(label: string): string {
  return SHAPES[label] ?? "rectangle";
}

function after(sep: string, s: string): string {
  const i = s.lastIndexOf(sep);
  return i >= 0 ? s.slice(i + 1) : s;
}

function trunc(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** Short badge text per label (05 §7.4); the full name lives in the tooltip and the table. */
export function badgeFor(node: GraphNode): string {
  const { label, key, title } = node;
  switch (label) {
    case "KEP": {
      const n = numberFromPath(key);
      return n !== null ? `KEP-${n}` : trunc(after("/", key), 24);
    }
    case "Person":
      return `@${key}`;
    case "SIG":
    case "WorkingGroup":
    case "Committee":
    case "Release":
    case "FeatureGate":
      return key;
    case "PullRequest":
    case "Issue":
      return `#${after("#", key)}`;
    case "Commit":
      return after("@", key).slice(0, 7);
    case "Review":
      return title ? trunc(title, 24) : "review";
    case "Comment":
      return trunc(title ?? "comment", 24);
    case "StatusChange":
      return trunc(title ?? "status change", 28);
    case "Decision":
      return trunc(title ?? "decision", 24);
    case "Document":
      return trunc(title ?? after("/", key), 24);
    case "Section":
      return trunc(title ?? after("#", key), 24);
    case "Finding": {
      const parts = key.split(":");
      return parts.length > 1 ? parts[1] : "finding";
    }
    default:
      return `${label.toUpperCase()} ${trunc(title ?? key, 20)}`;
  }
}

/** Full, human-readable name of a node. */
export function nameFor(node: GraphNode): string {
  const badge = badgeFor(node);
  return node.title && node.title !== badge ? `${badge} ${node.title}` : badge;
}
