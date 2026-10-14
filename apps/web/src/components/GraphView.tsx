"use client";

import { useEffect, useRef, useState } from "react";
import type { Core, ElementDefinition, LayoutOptions, StylesheetJson } from "cytoscape";
import type { GraphOut } from "@/lib/api/types";
import { badgeFor, nameFor, shapeFor } from "@/lib/graph";

/** Nodes drawn on the canvas; the table twin always lists all of them. */
const CAP = 200;

type CytoscapeFactory = typeof import("cytoscape");
let loader: Promise<CytoscapeFactory> | null = null;

function loadCytoscape(): Promise<CytoscapeFactory> {
  if (!loader) {
    loader = Promise.all([import("cytoscape"), import("cytoscape-dagre"), import("cytoscape-fcose")]).then(
      ([cy, dagre, fcose]) => {
        const factory = cy.default;
        factory.use(dagre.default);
        factory.use(fcose.default);
        return factory;
      },
    );
  }
  return loader;
}

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function stylesheet(): StylesheetJson {
  const c = {
    accent: token("--c-accent"),
    accentSubtle: token("--c-accent-subtle"),
    surface: token("--c-surface"),
    subtle: token("--c-surface-subtle"),
    strong: token("--c-border-strong"),
    text: token("--c-text-primary"),
    secondary: token("--c-text-secondary"),
    muted: token("--c-text-muted"),
  };
  const mono = getComputedStyle(document.body).getPropertyValue("--font-mono").trim() || "monospace";
  return [
    {
      selector: "node",
      style: {
        shape: "data(shape)" as never,
        label: "data(badge)",
        width: 28,
        height: 28,
        "background-color": c.subtle,
        "border-width": 1,
        "border-color": c.strong,
        color: c.muted,
        "font-family": mono,
        "font-size": 11,
        "text-valign": "bottom",
        "text-margin-y": 4,
        "text-wrap": "ellipsis",
        "text-max-width": "140px",
      },
    },
    {
      selector: "node.path",
      style: { "border-width": 2, "border-color": c.accent, "background-color": c.accentSubtle, color: c.text },
    },
    {
      selector: "node:selected",
      style: { "border-width": 3, "border-color": c.accent, "overlay-opacity": 0 },
    },
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": c.strong,
        "target-arrow-color": c.strong,
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        "arrow-scale": 0.8,
        label: "",
        "font-family": mono,
        "font-size": 10,
        color: c.secondary,
        "text-background-color": c.surface,
        "text-background-opacity": 1,
        "text-background-padding": "2px",
        "text-rotation": "autorotate",
      },
    },
    {
      selector: "edge.path",
      style: { width: 2, "line-color": c.accent, "target-arrow-color": c.accent, label: "data(type)" },
    },
    { selector: "edge.hover, edge.labelled", style: { label: "data(type)" } },
  ];
}

/** Cytoscape canvas: every arrow keeps the stored direction of its relationship; the layout is deterministic. */
export function GraphView({
  elements,
  layout,
  pathNodeIds = [],
  selectedKey = null,
  onSelect,
  onOpen,
  label,
  describedBy,
  height = 360,
}: {
  elements: GraphOut;
  layout: "dagre" | "fcose";
  /** Node ids to emphasise in accent (the cited nodes). */
  pathNodeIds?: string[];
  selectedKey?: string | null;
  onSelect?: (key: string | null) => void;
  onOpen?: (key: string) => void;
  /** Accessible summary of the graph. */
  label: string;
  /** id of the table that describes the graph. */
  describedBy?: string;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const handlers = useRef({ onSelect, onOpen });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    handlers.current = { onSelect, onOpen };
  }, [onSelect, onOpen]);

  const shown = elements.nodes.slice(0, CAP);
  const truncated = elements.nodes.length > shown.length;
  const dataKey = JSON.stringify([elements, layout, pathNodeIds]);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return;
    const pathSet = new Set(pathNodeIds);
    const nodes = elements.nodes.slice(0, CAP);
    const ids = new Set(nodes.map((n) => n.id));
    const edges = elements.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    const defs: ElementDefinition[] = [
      ...nodes.map((n) => ({
        group: "nodes" as const,
        data: { id: n.id, key: n.key, badge: badgeFor(n), shape: shapeFor(n.label), name: nameFor(n) },
        classes: pathSet.has(n.id) ? "path" : "",
      })),
      ...edges.map((e, i) => ({
        group: "edges" as const,
        data: { id: `e${i}`, source: e.source, target: e.target, type: e.type },
        classes: [pathSet.has(e.source) && pathSet.has(e.target) ? "path" : "", edges.length <= 30 ? "labelled" : ""].join(" "),
      })),
    ];

    loadCytoscape()
      .then((cytoscape) => {
        if (cancelled || !containerRef.current) return;
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const cy = cytoscape({
          container: containerRef.current,
          elements: defs,
          style: stylesheet(),
          boxSelectionEnabled: false,
          minZoom: 0.2,
          maxZoom: 3,
        });
        cyRef.current = cy;
        const opts: LayoutOptions =
          layout === "dagre"
            ? ({ name: "dagre", rankDir: "LR", nodeSep: 30, rankSep: 70, animate: !reduced, animationDuration: 300, fit: true, padding: 24 } as LayoutOptions)
            : ({ name: "fcose", randomize: false, animate: !reduced, animationDuration: 300, fit: true, padding: 24, nodeRepulsion: 6000 } as LayoutOptions);
        cy.layout(opts).run();
        cy.on("tap", "node", (evt) => handlers.current.onSelect?.(evt.target.data("key") as string));
        cy.on("tap", (evt) => {
          if (evt.target === cy) handlers.current.onSelect?.(null);
        });
        cy.on("dbltap", "node", (evt) => handlers.current.onOpen?.(evt.target.data("key") as string));
        cy.on("mouseover", "edge", (evt) => evt.target.addClass("hover"));
        cy.on("mouseout", "edge", (evt) => evt.target.removeClass("hover"));
        cy.on("mouseover", "node", (evt) => {
          if (containerRef.current) containerRef.current.title = evt.target.data("name") as string;
        });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    // Restyle when the theme changes (tokens are read from CSS variables).
    const observer = new MutationObserver(() => cyRef.current?.style(stylesheet()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return () => {
      cancelled = true;
      observer.disconnect();
      cyRef.current?.destroy();
      cyRef.current = null;
    };
    // dataKey captures every input that changes the drawing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataKey]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().unselect();
    if (selectedKey) cy.nodes().filter((n) => n.data("key") === selectedKey).select();
  }, [selectedKey]);

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const cy = cyRef.current;
    if (!cy) return;
    if (e.key === "+" || e.key === "=") {
      cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    } else if (e.key === "-") {
      cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
    } else if (e.key === "0") {
      cy.fit(undefined, 24);
    } else if (e.key === "Escape") {
      onSelect?.(null);
    } else if (e.key === "Enter" && selectedKey) {
      onOpen?.(selectedKey);
    } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      const keys = shown.map((n) => n.key);
      const cur = selectedKey ? keys.indexOf(selectedKey) : -1;
      const next = e.key === "ArrowRight" ? Math.min(cur + 1, keys.length - 1) : Math.max(cur - 1, 0);
      onSelect?.(keys[next]);
    } else {
      return;
    }
    e.preventDefault();
  }

  if (failed) {
    return <p className="text-sm text-fg-secondary">The graph view could not be loaded; the table below lists the same nodes and edges.</p>;
  }

  return (
    <div>
      <div
        ref={containerRef}
        tabIndex={0}
        role="img"
        aria-label={label}
        aria-describedby={describedBy}
        onKeyDown={onKeyDown}
        className="w-full rounded-md border border-border bg-surface"
        style={{ height }}
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-fg-muted">
        <span>
          {truncated ? `Showing ${shown.length} of ${elements.nodes.length} nodes. ` : ""}Keys: + and - zoom, 0 fits, arrows step between nodes, Enter opens.
        </span>
        <button type="button" className="quiet-link" onClick={() => cyRef.current?.fit(undefined, 24)}>
          Fit to view
        </button>
      </div>
    </div>
  );
}
