import type { GraphEdge, GraphNode, GraphOut, ToolResult } from "./api/types";

/** Best-effort label for a node the tool named only by key (03 §3.1 key formats); evidence records override it. */
function labelFromKey(key: string): string {
  if (key.startsWith("keps/")) return "KEP";
  if (key.startsWith("fnd:")) return "Finding";
  if (key.startsWith("dec:")) return "Decision";
  if (/^[a-z]+-[a-z-]+$/.test(key) && (key.startsWith("sig-") || key.startsWith("wg-"))) return "SIG";
  if (/^v\d+\.\d+$/.test(key)) return "Release";
  if (/@[0-9a-f]{7,40}$/.test(key)) return "Commit";
  if (/^[\w.-]+\/[\w.-]+#\d+$/.test(key)) return "Ticket";
  if (key.includes("#") && key.includes("/")) return "Section";
  if (key.includes(":") && key.includes("/")) return "Document";
  if (/^[A-Z][A-Za-z0-9]+$/.test(key)) return "FeatureGate";
  if (/^[a-z0-9-]+$/.test(key)) return "Person";
  return "Node";
}

interface DirectedEdge {
  type: string;
  from: string;
  to: string;
}

/** `rows[].edges` and `rows[].path_edges`, when a tool reports the stored direction of each hop. */
function directedEdges(rows: Record<string, unknown>[]): Set<string> {
  const out = new Set<string>();
  const visit = (v: unknown) => {
    if (!Array.isArray(v)) return;
    for (const e of v) {
      if (typeof e !== "object" || e === null) continue;
      const d = e as Partial<DirectedEdge>;
      if (typeof d.type === "string" && typeof d.from === "string" && typeof d.to === "string") out.add(`${d.type}\u0000${d.from}\u0000${d.to}`);
    }
  };
  for (const r of rows) {
    visit(r.edges);
    visit(r.path_edges);
  }
  return out;
}

/**
 * The subgraph a tool traversed: `paths` alternate node keys and relationship types
 * (`[key, REL, key, REL, key]`). Arrows follow the stored direction when the rows report it.
 */
export function pathsToGraph(result: ToolResult): GraphOut {
  const byKey = new Map(result.evidence.map((e) => [e.key, e]));
  const stored = directedEdges(result.rows);
  const nodes = new Map<string, GraphNode>();
  const edges = new Map<string, GraphEdge>();
  const node = (key: string) => {
    if (nodes.has(key)) return;
    const ev = byKey.get(key);
    nodes.set(key, {
      id: key,
      key,
      label: ev?.label ?? labelFromKey(key),
      title: ev?.title ?? null,
      url: ev?.url ?? null,
    });
  };
  for (const path of result.paths) {
    if (path.length === 0 || path.length % 2 === 0) continue;
    node(path[0]);
    for (let i = 1; i + 1 < path.length; i += 2) {
      const a = path[i - 1];
      const type = path[i];
      const b = path[i + 1];
      node(b);
      const reversed = stored.has(`${type}\u0000${b}\u0000${a}`) && !stored.has(`${type}\u0000${a}\u0000${b}`);
      const edge: GraphEdge = reversed ? { source: b, target: a, type } : { source: a, target: b, type };
      edges.set(`${edge.source}\u0000${edge.type}\u0000${edge.target}`, edge);
    }
  }
  return { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()) };
}
