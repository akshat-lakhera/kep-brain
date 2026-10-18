"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceRadial, forceSimulation, forceX, forceY } from "d3-force";
import type { Citation, GraphNode, GraphOut } from "@/lib/api/types";
import { badgeFor } from "@/lib/graph";
import { legendOrder, paintFor } from "@/lib/graphColors";
import { pageHref } from "@/lib/routes";
import { cx } from "./ui";

const W = 800;
const PAD = 24;
const R_MIN = 6;
const R_MAX = 14;
/** Up to this many nodes the drawing is small: every node is named, edges carry arrowheads and the box is shorter. */
const SMALL = 30;
/** Above SMALL nodes, radii are capped so a crowded drawing stays open; a SIG hub may still be drawn at R_HUB. */
const R_CAP = 12;
const R_HUB = 14;
/** A node with this many relations is a hub: it is named in a large drawing and its name is placed first. */
const HUB_DEGREE = 3;
/** Labels that organise a drawing and are always named: the owners and the releases. */
const HUB_LABELS = new Set(["SIG", "WorkingGroup", "Committee", "Release"]);
const LABEL_CHARS = 20;
const FONT = 11;
/** About the width of one mono character at 11px, for the room a label needs. */
const CH = 6.6;

interface Placed {
  node: GraphNode;
  x: number;
  y: number;
  r: number;
  degree: number;
  /** The text a label would show: the badge, or just "finding" for a Finding (its kind is never drawn). */
  text: string;
  /** SIG-like, or marked: pulled to the centre and named first. */
  hub: boolean;
}

interface PlacedEdge {
  type: string;
  source: Placed;
  target: Placed;
}

interface PlacedLabel {
  id: string;
  text: string;
  x: number;
  y: number;
  anchor: "start" | "middle" | "end";
}

interface Layout {
  nodes: Placed[];
  edges: PlacedEdge[];
  labels: PlacedLabel[];
  height: number;
}

interface SimNode {
  id: string;
  r: number;
  /** The ring the radial force pulls this node towards: 0 for hubs, the outer ring for leaves. */
  ring: number;
  /** The label's approximate width in px, for spacing in a small drawing. */
  label: number;
  x?: number;
  y?: number;
}

interface Rect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Two decimals: the server and the browser lay the graph out independently, and their last-digit float differences must not reach the markup. */
const r2 = (v: number) => Math.round(v * 100) / 100;

const trunc = (s: string) => (s.length > LABEL_CHARS ? `${s.slice(0, LABEL_CHARS - 1)}…` : s);

function overlaps(a: Rect, b: Rect, gap: number): boolean {
  return a.x0 < b.x1 + gap && b.x0 < a.x1 + gap && a.y0 < b.y1 + gap && b.y0 < a.y1 + gap;
}

/** Whether a label box touches a node's circle (nearest point of the box to the centre, against the radius). */
function hitsCircle(rect: Rect, p: Placed): boolean {
  const nx = Math.max(rect.x0, Math.min(p.x, rect.x1));
  const ny = Math.max(rect.y0, Math.min(p.y, rect.y1));
  return Math.hypot(nx - p.x, ny - p.y) < p.r + 2;
}

/**
 * The places a label may go, in order of preference: below-right of the node, above it, to its left; then, as a
 * last resort, centred below or to the right.
 */
function candidates(p: Placed, w: number): { anchor: PlacedLabel["anchor"]; x: number; y: number; rect: Rect }[] {
  const at = (anchor: PlacedLabel["anchor"], x: number, y: number) => {
    const x0 = anchor === "start" ? x : anchor === "middle" ? x - w / 2 : x - w;
    return { anchor, x: r2(x), y: r2(y), rect: { x0, y0: y - FONT, x1: x0 + w, y1: y + 3 } };
  };
  return [
    at("start", p.x + p.r * 0.7 + 3, p.y + p.r + FONT),
    at("middle", p.x, p.y - p.r - 5),
    at("end", p.x - p.r - 4, p.y + 4),
    at("middle", p.x, p.y + p.r + FONT + 1),
    at("start", p.x + p.r + 4, p.y + 4),
  ];
}

/**
 * Which nodes are named, and where. Up to SMALL nodes every node is a candidate; above that only hubs, marked nodes and
 * SIG-like or Release nodes. A Finding is never named (the legend explains the red dots). Labels are placed greedily,
 * hubs first, and a label that would cover another label or any circle, or leave the box, is dropped: its node shows
 * its name on hover instead.
 */
function placeLabels(nodes: Placed[], width: number, height: number, small: boolean, marked: Set<string>): PlacedLabel[] {
  const wanted = nodes.filter((p) => p.node.label !== "Finding" && (small || p.hub || p.degree >= HUB_DEGREE || marked.has(p.node.id)));
  wanted.sort((a, b) => Number(b.hub) - Number(a.hub) || b.degree - a.degree || a.node.id.localeCompare(b.node.id));
  const taken: Rect[] = [];
  const out: PlacedLabel[] = [];
  for (const p of wanted) {
    const text = trunc(p.text);
    const w = text.length * CH;
    for (const c of candidates(p, w)) {
      const { rect } = c;
      if (rect.x0 < 2 || rect.y0 < 2 || rect.x1 > width - 2 || rect.y1 > height - 2) continue;
      if (taken.some((t) => overlaps(t, rect, 2))) continue;
      if (nodes.some((q) => q !== p && hitsCircle(rect, q))) continue;
      taken.push(rect);
      out.push({ id: p.node.id, text, x: c.x, y: c.y, anchor: c.anchor });
      break;
    }
  }
  return out;
}

/** Runs the force simulation to completion and returns every node with a position and a radius, fitted to a `width` box. */
function layout(graph: GraphOut, width: number, marked: Set<string>): Layout {
  const W = Math.max(280, width);
  const n = graph.nodes.length;
  const small = n <= SMALL;
  const H = small ? 360 : 480;
  const ids = new Set(graph.nodes.map((n) => n.id));
  const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const degs = graph.nodes.map((n) => degree.get(n.id) ?? 0);
  const lo = Math.min(...degs, 0);
  const hi = Math.max(...degs, 1);
  const isHub = (node: GraphNode) => HUB_LABELS.has(node.label) || marked.has(node.id);
  const radius = (node: GraphNode) => {
    const d = degree.get(node.id) ?? 0;
    const base = hi === lo ? (R_MIN + R_MAX) / 2 : R_MIN + ((d - lo) / (hi - lo)) * (R_MAX - R_MIN);
    if (small) return base;
    return HUB_LABELS.has(node.label) && d >= HUB_DEGREE ? R_HUB : Math.min(R_CAP, base);
  };
  const outer = Math.min(W, H) / 2 - PAD - 10;
  const ring = (node: GraphNode) => (isHub(node) ? 0 : (degree.get(node.id) ?? 0) <= 1 ? outer : outer * 0.45);
  const labelWidth = (node: GraphNode) => (node.label === "Finding" ? 0 : Math.min(badgeFor(node).length, LABEL_CHARS) * CH);
  const simNodes: SimNode[] = graph.nodes.map((node) => ({ id: node.id, r: r2(radius(node)), ring: ring(node), label: labelWidth(node) }));
  const simLinks = edges.map((e) => ({ source: e.source, target: e.target }));
  // Many nodes need more room and a stronger charge; a handful needs longer links so the names have air.
  const linkDistance = small ? Math.max(70, 150 - n * 6) : Math.max(30, 90 - n * 0.5);
  // Small drawings keep room beside each node for its name; large ones only keep the circles apart.
  const collide = forceCollide<SimNode>().radius((d) => d.r + (small ? 10 + d.label / 4 : 4));
  const sim = forceSimulation<SimNode>(simNodes)
    .force("link", forceLink<SimNode, { source: string | SimNode; target: string | SimNode }>(simLinks).id((d) => d.id).distance(linkDistance).strength(0.6))
    // A coarser Barnes-Hut approximation above SMALL nodes: the picture is the same, the ticks cost half.
    .force("charge", forceManyBody<SimNode>().strength(small ? -120 : -220).theta(small ? 0.9 : 1.5))
    .force("center", forceCenter(W / 2, H / 2))
    .force("x", forceX<SimNode>(W / 2).strength(0.04))
    // A wide, short box pulls harder towards the vertical centre so the drawing spreads along the width; a box
    // nearer to square lets it use its height.
    .force("y", forceY<SimNode>(H / 2).strength(Math.min(0.14, Math.max(0.04, 0.05 * (W / H)))))
    .stop();
  if (small) {
    sim.force("collide", collide).tick(300);
  } else {
    // A weak pull of hubs to the centre and leaves outward, so a large drawing reads as stars around its hubs.
    sim.force("radial", forceRadial<SimNode>((d) => d.ring, W / 2, H / 2).strength(0.06));
    // Collision does not cool with the simulation, so it is added once the forces have settled: the last 100 of the
    // 400 ticks (300 when the graph is smaller) pack the circles apart at a fraction of the cost.
    const ticks = n > 60 ? 400 : 300;
    sim.tick(ticks - 100);
    sim.force("collide", collide).tick(100);
  }

  // Fit the circles to the box with PAD on every side (scaled up by at most 1.6x), then clamp so none leaves it.
  const minX = Math.min(...simNodes.map((s) => (s.x ?? W / 2) - s.r));
  const maxX = Math.max(...simNodes.map((s) => (s.x ?? W / 2) + s.r));
  const minY = Math.min(...simNodes.map((s) => (s.y ?? H / 2) - s.r));
  const maxY = Math.max(...simNodes.map((s) => (s.y ?? H / 2) + s.r));
  const widest = small ? Math.max(...simNodes.map((s) => s.label), CH) : 0;
  const padX = small ? Math.min(W / 4, PAD + widest / 2) : PAD;
  const padY = small ? PAD + 6 : PAD;
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const scale = n === 1 ? 1 : Math.min(1.6, (W - 2 * padX) / spanX, (H - 2 * padY) / spanY);
  const offX = padX + (W - 2 * padX - spanX * scale) / 2 - minX * scale;
  const offY = padY + (H - 2 * padY - spanY * scale) / 2 - minY * scale;

  const byId = new Map<string, Placed>();
  const placed = graph.nodes.map((node, i) => {
    const s = simNodes[i];
    const p: Placed = {
      node,
      r: s.r,
      degree: degree.get(node.id) ?? 0,
      text: node.label === "Finding" ? "finding" : badgeFor(node),
      hub: isHub(node),
      x: r2(Math.min(W - s.r - 1, Math.max(s.r + 1, (s.x ?? W / 2) * scale + offX))),
      y: r2(Math.min(H - s.r - 1, Math.max(s.r + 1, (s.y ?? H / 2) * scale + offY))),
    };
    byId.set(node.id, p);
    return p;
  });
  return {
    nodes: placed,
    edges: edges.map((e) => ({ type: e.type, source: byId.get(e.source)!, target: byId.get(e.target)! })),
    labels: placeLabels(placed, W, H, small, marked),
    height: H,
  };
}

/** The point where a line from `a` meets the edge of `b`'s circle (so the arrowhead touches the ring, not the centre). */
function endAt(a: Placed, b: Placed, gap: number): { x: number; y: number } {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const d = b.r + gap;
  return { x: r2(b.x - (dx / len) * d), y: r2(b.y - (dy / len) * d) };
}

function describe(nodes: Placed[], edgeCount: number): string {
  const counts = new Map<string, number>();
  for (const p of nodes) counts.set(p.node.label, (counts.get(p.node.label) ?? 0) + 1);
  const parts = legendOrder(counts.keys()).map((l) => `${counts.get(l)} ${l}`);
  return `Diagram of ${nodes.length} nodes and ${edgeCount} relations: ${parts.join(", ")}. The list view names every relation.`;
}

/** The label's own text, placed where it fits beside its node inside the box: used for the name shown on hover. */
function hoverLabelFor(p: Placed, width: number, height: number): PlacedLabel {
  const text = trunc(p.text);
  const w = text.length * CH;
  const options = candidates(p, w);
  const c = options.find(({ rect }) => rect.x0 >= 2 && rect.y0 >= 2 && rect.x1 <= width - 2 && rect.y1 <= height - 2) ?? options[0];
  return { id: p.node.id, text, x: c.x, y: c.y, anchor: c.anchor };
}

const labelStyle = {
  fontSize: FONT,
  stroke: "var(--c-surface)",
  strokeWidth: 3,
  paintOrder: "stroke" as const,
  strokeLinejoin: "round" as const,
};

/**
 * A force-directed drawing of a graph, laid out once before the first paint (no motion). Nodes are coloured by label
 * and sized by degree; cited or highlighted nodes carry an accent ring. Small drawings name every node; large ones name
 * the hubs and show the other names on hover, when a node's relations and neighbours also stand out. Hovering an edge
 * names the relation; clicking a node opens its page, or its source in a new tab.
 */
export function GraphView({
  graph,
  highlightIds,
  citations,
  className,
}: {
  graph: GraphOut;
  highlightIds?: string[];
  citations?: Citation[];
  className?: string;
}) {
  const router = useRouter();
  const markerId = useId();
  // The drawing is laid out at the box's own pixel width, so 11px labels are 11px: the server and the first client
  // render use the default width; the box is measured afterwards and the layout re-run once if it differs.
  const boxRef = useRef<HTMLElement>(null);
  const [width, setWidth] = useState(W);
  useEffect(() => {
    const el = boxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver((entries) => {
      const w = Math.round(entries[0]?.contentRect.width ?? 0);
      if (w > 0) setWidth((prev) => (Math.abs(prev - w) > 16 ? w : prev));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const highlightKey = (highlightIds ?? []).join("\u0000");
  const highlight = useMemo(() => new Set(highlightKey ? highlightKey.split("\u0000") : []), [highlightKey]);
  const cited = useMemo(() => new Set((citations ?? []).map((c) => c.key)), [citations]);
  const marked = useMemo(() => new Set(graph.nodes.filter((n) => highlight.has(n.id) || cited.has(n.key)).map((n) => n.id)), [graph, highlight, cited]);
  const { nodes, edges, labels, height } = useMemo(() => layout(graph, width, marked), [graph, width, marked]);
  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const e of edges) {
      const a = e.source.node.id;
      const b = e.target.node.id;
      (m.get(a) ?? m.set(a, new Set()).get(a)!).add(b);
      (m.get(b) ?? m.set(b, new Set()).get(b)!).add(a);
    }
    return m;
  }, [edges]);
  const labelled = useMemo(() => new Set(labels.map((l) => l.id)), [labels]);
  const legend = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of nodes) counts.set(p.node.label, (counts.get(p.node.label) ?? 0) + 1);
    return legendOrder(counts.keys()).map((label) => ({ label, count: counts.get(label) ?? 0, paint: paintFor(label) }));
  }, [nodes]);
  // The hovered (or focused) node: its edges and neighbours keep their colour, the rest dims, and an unnamed node
  // shows its name. Classes and one extra text element only; the layout is untouched.
  const [hover, setHover] = useState<string | null>(null);

  if (nodes.length === 0) return null;
  const small = nodes.length <= SMALL;
  const boxW = Math.max(280, width);
  const arrow = `arrow-${markerId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const near = hover === null ? null : new Set([hover, ...(neighbours.get(hover) ?? [])]);
  const hovered = hover === null || labelled.has(hover) ? null : nodes.find((p) => p.node.id === hover);
  const hoverLabel = hovered ? hoverLabelFor(hovered, boxW, height) : null;
  const focusClass = (id: string) => (near === null ? null : near.has(id) ? "is-near" : "is-far");

  return (
    <figure ref={boxRef} className={cx("space-y-2", className)}>
      <svg
        viewBox={`0 0 ${boxW} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        // A group, not an image: the nodes inside are links that keyboard and screen-reader users reach by their titles.
        role="group"
        aria-label={describe(nodes, edges.length)}
        className={cx("block w-full rounded-md border border-border bg-surface", small ? "h-[360px]" : "h-[480px]")}
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <defs>
          <marker id={arrow} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--c-border-input)" />
          </marker>
        </defs>
        <g>
          {edges.map((e, i) => {
            const end = endAt(e.source, e.target, small ? 3 : 1);
            const start = endAt(e.target, e.source, 1);
            const a = e.source.node.id;
            const b = e.target.node.id;
            const cls = near === null ? null : a === hover || b === hover ? "is-near" : "is-far";
            return (
              <g key={`${a}-${e.type}-${b}-${i}`} className={cx("graph-edge", cls)}>
                <title>{`${badgeFor(e.source.node)} ${e.type} ${badgeFor(e.target.node)}`}</title>
                <line
                  x1={start.x}
                  y1={start.y}
                  x2={end.x}
                  y2={end.y}
                  stroke="var(--c-border-strong)"
                  strokeWidth={small ? 1.25 : 1}
                  strokeOpacity={small ? 1 : 0.55}
                  markerEnd={small ? `url(#${arrow})` : undefined}
                  suppressHydrationWarning
                />
                {/* A wider invisible stroke so the relation name is easy to hover. */}
                <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="transparent" strokeWidth={10} suppressHydrationWarning />
              </g>
            );
          })}
        </g>
        <g>
          {nodes.map((p) => {
            const paint = paintFor(p.node.label);
            const isMarked = marked.has(p.node.id);
            const href = pageHref(p.node);
            const name = p.node.label === "Finding" ? (p.node.title ?? "finding") : p.node.title && p.node.title !== p.text ? `${p.text} ${p.node.title}` : p.text;
            const title = `${p.node.label}: ${name}${p.degree ? ` (${p.degree} relation${p.degree === 1 ? "" : "s"})` : ""}`;
            const body = (
              <>
                <title>{title}</title>
                {isMarked ? <circle cx={p.x} cy={p.y} r={p.r + 3.5} fill="none" stroke="var(--c-accent)" strokeWidth={2} suppressHydrationWarning /> : null}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.r}
                  fill={paint.hollow ? "var(--c-surface-subtle)" : paint.fill}
                  stroke={paint.hollow ? paint.fill : "var(--c-surface)"}
                  strokeWidth={paint.hollow ? 2 : 1.5}
                  suppressHydrationWarning
                />
              </>
            );
            const id = p.node.id;
            const cls = cx("graph-node", focusClass(id));
            const on = {
              onMouseEnter: () => setHover(id),
              onMouseLeave: () => setHover(null),
              onFocus: () => setHover(id),
              onBlur: () => setHover(null),
            };
            if (href) {
              return (
                <a
                  key={id}
                  href={href}
                  className={cls}
                  {...on}
                  onClick={(e) => {
                    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
                    e.preventDefault();
                    router.push(href);
                  }}
                >
                  {body}
                </a>
              );
            }
            if (p.node.url) {
              return (
                <a key={id} href={p.node.url} target="_blank" rel="noopener noreferrer" className={cls} {...on}>
                  {body}
                </a>
              );
            }
            return (
              <g key={id} className={cls} {...on}>
                {body}
              </g>
            );
          })}
        </g>
        {/* Names, drawn after every circle and edge with a halo in the surface colour, so they read over the lines. */}
        <g pointerEvents="none" aria-hidden="true">
          {labels.map((l) => (
            <text key={l.id} x={l.x} y={l.y} textAnchor={l.anchor} fill="var(--c-text-secondary)" className={cx("graph-label", near !== null && !near.has(l.id) && "is-far")} {...labelStyle} suppressHydrationWarning>
              {l.text}
            </text>
          ))}
          {hoverLabel ? (
            <text x={hoverLabel.x} y={hoverLabel.y} textAnchor={hoverLabel.anchor} fill="var(--c-text-primary)" {...labelStyle}>
              {hoverLabel.text}
            </text>
          ) : null}
        </g>
      </svg>
      <figcaption className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-secondary">
        {legend.map((l) => (
          <span key={l.label} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={l.paint.hollow ? { border: `2px solid ${l.paint.fill}`, background: "var(--c-surface-subtle)" } : { background: l.paint.fill }}
            />
            {l.label} <span className="tabular text-fg-muted">{l.count}</span>
          </span>
        ))}
        {highlight.size || cited.size ? (
          <span className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border-2 border-accent" />
            cited
          </span>
        ) : null}
        {!small ? <span className="text-fg-muted">hover a node for its name</span> : null}
      </figcaption>
    </figure>
  );
}
