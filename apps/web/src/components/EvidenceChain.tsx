"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useMemo, useState, useSyncExternalStore } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { Citation, GraphEdge, GraphNode, GraphOut } from "@/lib/api/types";
import { clientApi } from "@/lib/api/client";
import { badgeFor } from "@/lib/graph";
import { numberFromPath } from "@/lib/format";
import { CONTAINER_LABELS, CONTAINER_RELS, RANKS, phraseFor, rankFor, type Dir } from "@/lib/relations";
import { ExtLink, cx } from "./ui";

const CAP = 5;
const KEEP_OPEN_KEY = "kep-brain.chain.keep-open";

interface Indexed {
  nodes: Map<string, GraphNode>;
  out: Map<string, GraphEdge[]>;
  in: Map<string, GraphEdge[]>;
}

function indexGraph(g: GraphOut): Indexed {
  const nodes = new Map(g.nodes.map((n) => [n.id, n]));
  const out = new Map<string, GraphEdge[]>();
  const inn = new Map<string, GraphEdge[]>();
  for (const e of g.edges) {
    if (!nodes.has(e.source) || !nodes.has(e.target)) continue;
    out.set(e.source, [...(out.get(e.source) ?? []), e]);
    inn.set(e.target, [...(inn.get(e.target) ?? []), e]);
  }
  return { nodes, out, in: inn };
}

function mergeGraph(a: GraphOut, b: GraphOut): GraphOut {
  const nodes = new Map(a.nodes.map((n) => [n.id, n]));
  for (const n of b.nodes) nodes.set(n.id, nodes.get(n.id) ?? n);
  const seen = new Set(a.edges.map((e) => `${e.source}\0${e.type}\0${e.target}`));
  const edges = [...a.edges];
  for (const e of b.edges) {
    const k = `${e.source}\0${e.type}\0${e.target}`;
    if (!seen.has(k)) {
      seen.add(k);
      edges.push(e);
    }
  }
  return { nodes: [...nodes.values()], edges };
}

interface Row {
  node: GraphNode;
  /** Nodes shown inside this row because they live inside this PR or issue. */
  inside: { node: GraphNode; phrase: string }[];
}

interface Group {
  key: string;
  phrase: string;
  rank: number;
  rows: Row[];
  count: number;
}

/** The relation groups of one node, in the fixed order, with PR and issue contents nested under their container. */
function groupsOf(g: Indexed, id: string, hide: Set<string>): Group[] {
  const node = g.nodes.get(id);
  if (!node) return [];
  const raw = new Map<string, { phrase: string; rank: number; targets: GraphNode[] }>();
  const add = (type: string, dir: Dir, target: GraphNode) => {
    if (hide.has(target.id)) return;
    const key = `${dir}:${type}`;
    const cur = raw.get(key) ?? { phrase: phraseFor(type, dir), rank: rankFor(type), targets: [] };
    if (!cur.targets.some((t) => t.id === target.id)) cur.targets.push(target);
    raw.set(key, cur);
  };
  for (const e of g.out.get(id) ?? []) add(e.type, "out", g.nodes.get(e.target)!);
  for (const e of g.in.get(id) ?? []) add(e.type, "in", g.nodes.get(e.source)!);

  // A KEP's sections sit two hops away behind its document; show them as "why it is designed this way".
  if (node.label === "KEP") {
    const sections: GraphNode[] = [];
    for (const d of g.out.get(id) ?? []) {
      if (d.type !== "HAS_DOCUMENT") continue;
      for (const s of g.out.get(d.target) ?? []) {
        const t = g.nodes.get(s.target);
        if (s.type === "HAS_SECTION" && t && !hide.has(t.id) && !sections.some((x) => x.id === t.id)) sections.push(t);
      }
    }
    if (sections.length) {
      raw.set("why", { phrase: RANKS[0], rank: 0, targets: sections });
      raw.delete("out:HAS_DOCUMENT");
    }
  }

  const groups: Group[] = [];
  for (const [key, { phrase, rank, targets }] of raw) {
    // Nest a target under the PR or issue it belongs to when that container is also in this group.
    const containers = new Set(targets.filter((t) => CONTAINER_LABELS.has(t.label)).map((t) => t.id));
    const inside = new Map<string, Row["inside"]>();
    const rows: Row[] = [];
    for (const t of targets) {
      if (CONTAINER_LABELS.has(t.label)) continue;
      const link = (g.out.get(t.id) ?? []).find((e) => CONTAINER_RELS.has(e.type) && containers.has(e.target));
      if (link) {
        inside.set(link.target, [...(inside.get(link.target) ?? []), { node: t, phrase: phraseFor(link.type, "out") }]);
      } else rows.push({ node: t, inside: [] });
    }
    for (const t of targets) if (CONTAINER_LABELS.has(t.label)) rows.push({ node: t, inside: inside.get(t.id) ?? [] });
    rows.sort((a, b) => Number(CONTAINER_LABELS.has(b.node.label)) - Number(CONTAINER_LABELS.has(a.node.label)) || badgeFor(a.node).localeCompare(badgeFor(b.node), "en", { numeric: true }));
    groups.push({ key, phrase, rank, rows, count: targets.length });
  }
  groups.sort((a, b) => a.rank - b.rank || a.phrase.localeCompare(b.phrase));
  return groups;
}

export function pageHref(node: GraphNode): Route | null {
  if (node.label === "KEP") {
    const n = numberFromPath(node.key);
    return n !== null ? (`/explore/kep/${n}` as Route) : null;
  }
  if (node.label === "Person") return `/explore/person/${encodeURIComponent(node.key)}` as Route;
  if (node.label === "SIG") return `/explore/sig/${encodeURIComponent(node.key)}` as Route;
  if (node.label === "Finding") return `/audit?finding=${encodeURIComponent(node.key)}#findings` as Route;
  return null;
}

/** Pick one starting node per connected component: a KEP if there is one, else a highlighted node, else the first. */
function rootsOf(g: Indexed, order: GraphNode[], highlight: Set<string>): string[] {
  const seen = new Set<string>();
  const roots: string[] = [];
  for (const start of order) {
    if (seen.has(start.id)) continue;
    const comp: GraphNode[] = [];
    const stack = [start.id];
    seen.add(start.id);
    while (stack.length) {
      const id = stack.pop()!;
      comp.push(g.nodes.get(id)!);
      for (const e of [...(g.out.get(id) ?? []), ...(g.in.get(id) ?? [])]) {
        const other = e.source === id ? e.target : e.source;
        if (!seen.has(other)) {
          seen.add(other);
          stack.push(other);
        }
      }
    }
    const pick = comp.find((n) => n.label === "KEP") ?? comp.find((n) => highlight.has(n.id)) ?? comp[0];
    roots.push(pick.id);
  }
  return roots;
}

/** Paths (root>…>node) to open at first render so every highlighted node is visible. */
function initialOpen(g: Indexed, roots: string[], highlight: Set<string>): { nodes: Set<string>; groups: Set<string> } {
  const nodes = new Set<string>();
  const groups = new Set<string>();
  if (highlight.size === 0) return { nodes, groups };
  for (const root of roots) {
    const parent = new Map<string, string | null>([[root, null]]);
    const queue = [root];
    while (queue.length) {
      const id = queue.shift()!;
      for (const e of [...(g.out.get(id) ?? []), ...(g.in.get(id) ?? [])]) {
        const other = e.source === id ? e.target : e.source;
        if (!parent.has(other)) {
          parent.set(other, id);
          queue.push(other);
        }
      }
    }
    const pathOf = (id: string): string[] => {
      const p: string[] = [];
      for (let cur: string | null = id; cur !== null; cur = parent.get(cur) ?? null) p.unshift(cur);
      return p;
    };
    for (const h of highlight) {
      if (!parent.has(h)) continue;
      const p = pathOf(h);
      // Open every node on the way (not the highlighted leaf itself) and every group that holds the next hop.
      for (let i = 0; i < p.length - 1; i += 1) {
        const path = p.slice(0, i + 1).join(">");
        nodes.add(path);
        const gs = groupsOf(g, p[i], new Set(p.slice(0, i)));
        const next = p[i + 1];
        for (const grp of gs) {
          if (grp.rows.some((r) => r.node.id === next || r.inside.some((x) => x.node.id === next))) groups.add(`${path}#${grp.key}`);
        }
      }
    }
  }
  return { nodes, groups };
}

const keepOpenListeners = new Set<() => void>();

function readKeepOpen(): boolean {
  try {
    return window.localStorage.getItem(KEEP_OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function writeKeepOpen(v: boolean) {
  try {
    window.localStorage.setItem(KEEP_OPEN_KEY, v ? "1" : "0");
  } catch {
    // per-viewer convenience only
  }
  for (const l of keepOpenListeners) l();
}

function subscribeKeepOpen(cb: () => void) {
  keepOpenListeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    keepOpenListeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}

/**
 * The evidence chain: a graph shown as rows you open. Each node lists its relations in words, grouped and in a fixed
 * order; a relation opens to its targets; a target opens in place with its own relations, fetched on demand. Pull
 * requests and issues hold what happened inside them. One node open per level unless "keep open" is on.
 */
export function EvidenceChain({
  graph,
  rootIds,
  highlightIds,
  citations,
  label,
  emptyText,
  expandable = true,
}: {
  graph: GraphOut;
  /** Starting nodes; by default one per connected component. */
  rootIds?: string[];
  /** Nodes to mark and pre-open along the way (the cited path). */
  highlightIds?: string[];
  citations?: Citation[];
  label: string;
  emptyText: string;
  /** Whether clicking a node may fetch its neighbourhood from the API. */
  expandable?: boolean;
}) {
  const [extra, setExtra] = useState<GraphOut>({ nodes: [], edges: [] });
  const merged = useMemo(() => mergeGraph(graph, extra), [graph, extra]);
  const g = useMemo(() => indexGraph(merged), [merged]);
  const highlight = useMemo(() => new Set(highlightIds ?? []), [highlightIds]);
  const roots = useMemo(() => rootIds?.filter((id) => g.nodes.has(id)) ?? rootsOf(g, graph.nodes, highlight), [rootIds, g, graph.nodes, highlight]);
  const seed = useMemo(() => initialOpen(indexGraph(graph), roots, highlight), [graph, roots, highlight]);
  const [openNodes, setOpenNodes] = useState<Set<string>>(() => seed.nodes);
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => seed.groups);
  const [showAll, setShowAll] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const keepOpen = useSyncExternalStore(subscribeKeepOpen, readKeepOpen, () => false);
  // When the seed graph changes (an answer streaming in), re-open along the new cited path.
  const [seedUsed, setSeedUsed] = useState(seed);
  if (seedUsed !== seed) {
    setSeedUsed(seed);
    setOpenNodes(seed.nodes);
    setOpenGroups(seed.groups);
  }

  const citeByKey = useMemo(() => {
    const m = new Map<string, number[]>();
    for (const c of citations ?? []) m.set(c.key, [...(m.get(c.key) ?? []), c.index]);
    return m;
  }, [citations]);

  const fetchAround = useCallback(
    async (node: GraphNode) => {
      if (!expandable || expanded.has(node.id) || loading.has(node.id)) return;
      setLoading((s) => new Set(s).add(node.id));
      const res = await clientApi.neighborhood(node.key);
      setLoading((s) => {
        const n = new Set(s);
        n.delete(node.id);
        return n;
      });
      setExpanded((s) => new Set(s).add(node.id));
      if (res.ok) setExtra((e) => mergeGraph(e, res.data));
    },
    [expandable, expanded, loading],
  );

  function toggleNode(path: string, parentPath: string, node: GraphNode) {
    const isOpen = openNodes.has(path);
    setOpenNodes((s) => {
      const n = new Set<string>();
      for (const p of s) {
        if (p === path || p.startsWith(`${path}>`)) continue; // closing this branch
        if (!isOpen && !keepOpen && p.startsWith(`${parentPath}>`) && p !== parentPath) continue; // accordion: close siblings
        n.add(p);
      }
      if (!isOpen) n.add(path);
      return n;
    });
    if (!isOpen) void fetchAround(node);
  }

  function toggleGroup(key: string) {
    setOpenGroups((s) => {
      const n = new Set(s);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  }

  const setKeep = writeKeepOpen;

  if (graph.nodes.length === 0) return <p className="text-fg-secondary">{emptyText}</p>;

  function renderNode(id: string, parentPath: string, ancestors: Set<string>, depth: number, phrase?: string, cited?: number[]) {
    const node = g.nodes.get(id);
    if (!node) return null;
    const path = parentPath ? `${parentPath}>${id}` : id;
    const isOpen = openNodes.has(path);
    const isRoot = depth === 0;
    const href = pageHref(node);
    const cites = cited ?? citeByKey.get(node.key) ?? [];
    const marked = highlight.has(id);
    return (
      <li key={path} className={cx(depth > 0 && "border-l border-border pl-3")}>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 py-1">
          {phrase ? <span className="text-xs text-fg-muted">{phrase}</span> : null}
          <button
            type="button"
            aria-expanded={isOpen}
            onClick={() => toggleNode(path, parentPath, node)}
            className={cx("inline-flex items-center gap-1 rounded-sm px-1 font-mono text-sm hover:bg-surface-subtle", marked && "bg-accent-subtle text-accent", isRoot && "font-semibold")}
            title={isOpen ? "Fold" : "Open"}
          >
            {isOpen ? <ChevronDown aria-hidden="true" size={14} strokeWidth={1.5} /> : <ChevronRight aria-hidden="true" size={14} strokeWidth={1.5} />}
            {badgeFor(node)}
          </button>
          <span className="text-xs text-fg-muted">{node.label}</span>
          {node.title && node.title !== badgeFor(node) ? <span className="min-w-0 truncate text-sm" title={node.title}>{node.title}</span> : null}
          {cites.map((n) => (
            <a key={n} href={`#source-${n}`} className="inline-flex min-h-5 min-w-5 items-center justify-center rounded-sm bg-accent-subtle px-1 font-mono text-xs text-accent" aria-label={`Source ${n}`}>
              {n}
            </a>
          ))}
          {href ? (
            <Link href={href} className="quiet-link text-xs">
              open page
            </Link>
          ) : node.url ? (
            <ExtLink href={node.url} label={`${badgeFor(node)} source`}>
              <span className="text-xs">source</span>
            </ExtLink>
          ) : null}
          {loading.has(id) ? <span className="text-xs text-fg-muted">loading…</span> : null}
        </div>
        {isOpen ? renderGroups(node, path, new Set([...ancestors, id]), depth + 1) : null}
      </li>
    );
  }

  function renderGroups(node: GraphNode, path: string, ancestors: Set<string>, depth: number) {
    const groups = groupsOf(g, node.id, ancestors);
    if (groups.length === 0) {
      return (
        <p className="border-l border-border py-1 pl-3 text-xs text-fg-muted">
          {loading.has(node.id) ? "loading…" : expanded.has(node.id) || !expandable ? "nothing further is connected" : "no further relation loaded"}
        </p>
      );
    }
    return (
      <ul className="border-l border-border pl-3">
        {groups.map((grp) => {
          const gkey = `${path}#${grp.key}`;
          const open = openGroups.has(gkey);
          const all = showAll.has(gkey);
          const rows = all ? grp.rows : grp.rows.slice(0, CAP);
          return (
            <li key={gkey} className="py-0.5">
              <button type="button" aria-expanded={open} onClick={() => toggleGroup(gkey)} className="inline-flex items-center gap-1 text-sm text-fg-secondary hover:text-fg">
                {open ? <ChevronDown aria-hidden="true" size={14} strokeWidth={1.5} /> : <ChevronRight aria-hidden="true" size={14} strokeWidth={1.5} />}
                {grp.phrase} <span className="tabular text-fg-muted">({grp.count})</span>
              </button>
              {open ? (
                <ul className="ml-1">
                  {rows.map((r) => (
                    <li key={r.node.id}>
                      {renderNode(r.node.id, path, ancestors, depth)}
                      {r.inside.length ? (
                        <ul className="ml-6 border-l border-border pl-3">
                          {r.inside.map((x) => (
                            <li key={x.node.id}>{renderNode(x.node.id, `${path}>${r.node.id}`, new Set([...ancestors, r.node.id]), depth + 1, x.phrase)}</li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                  {grp.rows.length > CAP && !all ? (
                    <li>
                      <button type="button" className="quiet-link py-1 text-xs" onClick={() => setShowAll((s) => new Set(s).add(gkey))}>
                        +{grp.rows.length - CAP} more
                      </button>
                    </li>
                  ) : null}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-fg-muted">
        <span>
          {merged.nodes.length.toLocaleString("en-US")} nodes · {merged.edges.length.toLocaleString("en-US")} relations
          {highlight.size ? " · highlighted rows are cited" : ""}
        </span>
        <label className="inline-flex items-center gap-1.5">
          <input type="checkbox" checked={keepOpen} onChange={(e) => setKeep(e.target.checked)} />
          keep open
        </label>
      </div>
      <ul aria-label={label} className="text-sm">
        {roots.map((r) => renderNode(r, "", new Set(), 0))}
      </ul>
    </div>
  );
}
