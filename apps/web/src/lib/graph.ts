import type { GraphEdge, GraphNode, GraphOut } from "./api/types";
import { numberFromPath } from "./format";

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

/** Union of two graphs: nodes by id (first wins), edges by source, type and target. */
export function mergeGraph(a: GraphOut, b: GraphOut): GraphOut {
  const nodes = new Map(a.nodes.map((n) => [n.id, n]));
  for (const n of b.nodes) if (!nodes.has(n.id)) nodes.set(n.id, n);
  const key = (e: GraphEdge) => `${e.source}\u0000${e.type}\u0000${e.target}`;
  const edges = new Map(a.edges.map((e) => [key(e), e]));
  for (const e of b.edges) if (!edges.has(key(e))) edges.set(key(e), e);
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}
