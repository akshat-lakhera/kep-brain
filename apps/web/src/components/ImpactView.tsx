import type { ReactNode } from "react";
import type { ToolResult } from "@/lib/api/types";
import { numberFromPath, pluralS } from "@/lib/format";
import { ToolResultView } from "./ToolResultView";
import { EmptyState, ExtLink, KepLink, PersonLink, SigLink } from "./ui";

/** A graph node as the tool returns it inside a row: label, key, title, url and the node's own properties. */
interface NodeRow {
  label: string;
  key: string;
  title?: string | null;
  url?: string | null;
  [prop: string]: unknown;
}

type Group = "keps" | "feature_gates" | "sigs" | "people" | "open_issues";

const GROUPS: { field: Group; label: string }[] = [
  { field: "keps", label: "KEPs" },
  { field: "feature_gates", label: "Feature gates" },
  { field: "sigs", label: "SIGs" },
  { field: "people", label: "Authors and approvers" },
  { field: "open_issues", label: "Open tracking issues" },
];

const HOP_TEXT: Record<number, string> = {
  1: "One step away: KEPs this one replaces, is replaced by, refers to or shares a feature gate with, and its own SIG, authors, approvers and open tracking issue.",
  2: "Two steps away, including the SIG, authors, approvers and open issue of each KEP at hop 1.",
  3: "Three steps away.",
};

function isNodeRow(v: unknown): v is NodeRow {
  return typeof v === "object" && v !== null && typeof (v as NodeRow).label === "string" && typeof (v as NodeRow).key === "string";
}

function nodes(v: unknown): NodeRow[] {
  return Array.isArray(v) ? v.filter(isNodeRow) : [];
}

function Node({ n }: { n: NodeRow }): ReactNode {
  if (n.label === "KEP") {
    const num = numberFromPath(n.key);
    return (
      <span className="flex flex-wrap items-baseline gap-x-2">
        <KepLink number={num} label={num !== null ? `KEP-${num}` : n.key} />
        {n.title ? <span className="text-sm">{n.title}</span> : null}
      </span>
    );
  }
  if (n.label === "Person") return <PersonLink login={n.key} />;
  if (n.label === "SIG") return <SigLink sig={n.key} />;
  if (n.label === "Issue") {
    return (
      <span className="flex flex-wrap items-baseline gap-x-2">
        <ExtLink href={n.url}>
          <span className="font-mono">{typeof n.number === "number" ? `#${n.number}` : n.key}</span>
        </ExtLink>
        {n.title ? <span className="text-sm">{n.title}</span> : null}
      </span>
    );
  }
  return n.url ? (
    <ExtLink href={n.url}>
      <span className="font-mono break-all">{n.title ?? n.key}</span>
    </ExtLink>
  ) : (
    <span className="font-mono break-all">{n.title ?? n.key}</span>
  );
}

/**
 * The `impact_of_change` result as a reader wants it: what is reached, hop by hop, each node linked to its page or source.
 * The raw rows, evidence, paths and Cypher stay one disclosure away.
 */
export function ImpactView({ name, params, result }: { name: string; params: Record<string, unknown>; result: ToolResult }) {
  const head = result.rows[0];
  const hops = result.rows
    .slice(1)
    .filter((r) => typeof r.hop === "number")
    .map((r) => ({ hop: r.hop as number, groups: GROUPS.map((g) => ({ ...g, nodes: nodes(r[g.field]) })).filter((g) => g.nodes.length > 0) }));
  const reached = typeof head?.reached === "number" ? head.reached : null;
  const depth = typeof head?.depth === "number" ? head.depth : null;
  const raw = (
    <details className="group">
      <summary className="cursor-pointer text-sm text-fg-secondary hover:text-fg">
        Rows, evidence, paths and the Cypher behind this ({result.rows.length} row{pluralS(result.rows.length)}, {result.paths.length} path
        {pluralS(result.paths.length)})
      </summary>
      <div className="reveal mt-3">
        <ToolResultView name={name} params={params} result={result} />
      </div>
    </details>
  );

  if (reached === null || depth === null) {
    // Not the shape this view reads (for example an unresolved reference): show the generic result.
    return <ToolResultView name={name} params={params} result={result} />;
  }
  if (hops.length === 0) {
    return (
      <div className="space-y-3">
        <EmptyState title={`Nothing is linked to this KEP within ${depth} hops`}>
          No KEP replaces it, is replaced by it, refers to it or shares a feature gate with it.
        </EmptyState>
        {raw}
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <p className="text-sm text-fg-secondary">
        <strong className="tabular font-medium text-fg">{reached.toLocaleString("en-US")}</strong> node{pluralS(reached)} within{" "}
        <span className="tabular">{depth}</span> hops of this KEP, each with its shortest path back to it.
      </p>
      {hops.map(({ hop, groups }) => (
        <section key={hop} aria-labelledby={`impact-hop-${hop}`}>
          <h3 id={`impact-hop-${hop}`} className="eyebrow">
            Hop {hop}
          </h3>
          {HOP_TEXT[hop] ? <p className="mt-0.5 text-xs text-fg-muted">{HOP_TEXT[hop]}</p> : null}
          <dl className="mt-2 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            {groups.map((g) => (
              <div key={g.field} className="min-w-0">
                <dt className="text-sm text-fg-secondary">
                  {g.label} <span className="tabular text-fg-muted">({g.nodes.length})</span>
                </dt>
                <dd className="mt-0.5">
                  <ul className="space-y-1">
                    {g.nodes.map((n) => (
                      <li key={`${n.label}:${n.key}`} className="break-words">
                        <Node n={n} />
                      </li>
                    ))}
                  </ul>
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
      {raw}
    </div>
  );
}
