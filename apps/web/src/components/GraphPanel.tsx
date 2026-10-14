"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useId, useMemo, useState, useSyncExternalStore } from "react";
import type { GraphNode, GraphOut } from "@/lib/api/types";
import { badgeFor, nameFor, shapeFor } from "@/lib/graph";
import { numberFromPath } from "@/lib/format";
import { GraphView } from "./GraphView";
import { ExtLink, TableWrap, cx, tableClass, tdClass, thClass } from "./ui";

function subscribeWidth(cb: () => void) {
  const mq = window.matchMedia("(max-width: 767px)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

/** Graph canvas plus its accessible table twin, legend and a "Table only" switch (default under 768px). */
export function GraphPanel({
  graph,
  layout = "dagre",
  pathNodeIds,
  label,
  emptyText,
  height,
}: {
  graph: GraphOut;
  layout?: "dagre" | "fcose";
  pathNodeIds?: string[];
  label: string;
  emptyText: string;
  height?: number;
}) {
  const router = useRouter();
  const tableId = useId();
  const narrow = useSyncExternalStore(
    subscribeWidth,
    () => window.matchMedia("(max-width: 767px)").matches,
    () => false,
  );
  const [tableChoice, setTableChoice] = useState<boolean | null>(null);
  const tableOnly = tableChoice ?? narrow;
  const [selected, setSelected] = useState<string | null>(null);

  const byKey = useMemo(() => new Map(graph.nodes.map((n) => [n.key, n])), [graph]);
  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const labelsInUse = useMemo(() => Array.from(new Set(graph.nodes.map((n) => n.label))).sort(), [graph]);

  function open(key: string) {
    const node = byKey.get(key);
    if (!node) return;
    if (node.label === "KEP") {
      const n = numberFromPath(node.key);
      if (n !== null) {
        router.push(`/explore/kep/${n}` as Route);
        return;
      }
    }
    if (node.url) window.open(node.url, "_blank", "noopener,noreferrer");
  }

  if (graph.nodes.length === 0) {
    return <p className="text-fg-secondary">{emptyText}</p>;
  }

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-fg-secondary">
          {graph.nodes.length} nodes · {graph.edges.length} edges
        </p>
        <button
          type="button"
          aria-pressed={tableOnly}
          onClick={() => setTableChoice(!tableOnly)}
          className="h-7 rounded-sm border border-border-input px-2 text-sm"
        >
          Table only
        </button>
      </div>
      {!tableOnly ? (
        <>
          <GraphView
            elements={graph}
            layout={layout}
            pathNodeIds={pathNodeIds}
            selectedKey={selected}
            onSelect={setSelected}
            onOpen={open}
            label={label}
            describedBy={tableId}
            height={height}
          />
          <ul aria-label="Legend" className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-secondary">
            {labelsInUse.map((l) => (
              <li key={l}>
                <span className="font-mono">{l}</span> <span className="text-fg-muted">({shapeFor(l)})</span>
              </li>
            ))}
            {pathNodeIds?.length ? (
              <li>
                <span className="text-accent">blue outline</span> = cited node; grey = context
              </li>
            ) : null}
          </ul>
        </>
      ) : null}

      <div id={tableId} className="mt-3">
        <TableWrap label="Graph edges">
          <table className={tableClass}>
            <caption className="mb-1 text-left text-xs text-fg-muted">Edges in the stored direction.</caption>
            <thead>
              <tr>
                <th className={thClass}>Source</th>
                <th className={thClass}>Relationship</th>
                <th className={thClass}>Target</th>
              </tr>
            </thead>
            <tbody>
              {graph.edges.map((e, i) => {
                const s = byId.get(e.source);
                const t = byId.get(e.target);
                if (!s || !t) return null;
                return (
                  <tr key={i} className={cx(selected && (selected === s.key || selected === t.key) && "bg-accent-subtle")}>
                    <td className={tdClass}>
                      <NodeCell node={s} onSelect={setSelected} />
                    </td>
                    <td className={cx(tdClass, "font-mono whitespace-nowrap")}>—{e.type}→</td>
                    <td className={tdClass}>
                      <NodeCell node={t} onSelect={setSelected} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableWrap>
      </div>
    </div>
  );
}

function NodeCell({ node, onSelect }: { node: GraphNode; onSelect: (k: string) => void }) {
  const n = node.label === "KEP" ? numberFromPath(node.key) : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <button type="button" className="quiet-link font-mono" onClick={() => onSelect(node.key)} title={nameFor(node)}>
        {badgeFor(node)}
      </button>
      <span className="text-xs text-fg-muted">{node.label}</span>
      {n !== null ? null : node.url ? (
        <ExtLink href={node.url} label={`${nameFor(node)} source`}>
          <span className="text-xs">source</span>
        </ExtLink>
      ) : null}
    </span>
  );
}
