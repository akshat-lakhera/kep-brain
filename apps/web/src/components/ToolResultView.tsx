"use client";

import { memo, useMemo, useState } from "react";
import { Copy } from "lucide-react";
import type { ToolResult } from "@/lib/api/types";
import { ms, pluralS } from "@/lib/format";
import { pathsToGraph } from "@/lib/toolgraph";
import { RowsTable } from "./DataView";
import { EvidenceChain } from "./EvidenceChain";
import { Tabs } from "./Tabs";
import { useToast } from "./Toast";
import { Chip, EmptyState, ExtLink, cx } from "./ui";

/**
 * A ToolResult as a reader checks it: rows, evidence links, the traversed paths as an evidence chain, and the Cypher
 * template. Memoised: typing in the tool's form above must not re-render a large result.
 */
export const ToolResultView = memo(function ToolResultView({ name, params, result }: { name: string; params: Record<string, unknown>; result: ToolResult }) {
  const graph = useMemo(() => pathsToGraph(result), [result]);
  const n = result.rows.length;
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-fg-secondary">
        <span className="font-mono text-fg">{name}</span>
        <span>·</span>
        <span className="tabular">
          {n.toLocaleString("en-US")} row{pluralS(n)}
        </span>
        <span>·</span>
        <span className="tabular">
          {result.evidence.length.toLocaleString("en-US")} evidence record{pluralS(result.evidence.length)}
        </span>
        <span>·</span>
        <span className="tabular">
          {result.paths.length.toLocaleString("en-US")} path{pluralS(result.paths.length)}
        </span>
        <span>·</span>
        <span className="tabular">{ms(result.ms)}</span>
        {result.truncated ? <Chip tone="warning">truncated: the tool cut the result at its row limit</Chip> : null}
      </p>
      <Tabs
        label={`Result of ${name}`}
        tabs={[
          { id: "rows", label: `Rows (${n})`, content: <Rows result={result} /> },
          { id: "evidence", label: `Evidence (${result.evidence.length})`, content: <EvidenceLinks result={result} /> },
          { id: "paths", label: `Paths (${result.paths.length})`, content: <Paths result={result} graph={graph} /> },
          { id: "cypher", label: "Cypher", content: <Cypher name={name} params={params} template={result.template} /> },
        ]}
      />
    </div>
  );
});

function Rows({ result }: { result: ToolResult }) {
  if (result.rows.length === 0) {
    return <EmptyState title="The tool returned no rows">The graph holds nothing matching these parameters; the Cypher tab shows the query that ran.</EmptyState>;
  }
  return <RowsTable rows={result.rows} caption="Rows returned by the tool" maxCols={12} />;
}

function EvidenceLinks({ result }: { result: ToolResult }) {
  if (result.evidence.length === 0) {
    return <EmptyState title="No evidence records">This result carries no citable nodes; the rows are context only.</EmptyState>;
  }
  return (
    <ul className="space-y-1">
      {result.evidence.map((e) => (
        <li key={e.evidence_id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span className="font-mono text-xs text-fg-muted">{e.label}</span>
          <ExtLink href={e.url}>{e.title ?? e.key}</ExtLink>
          <span className="font-mono text-xs break-all text-fg-muted">{e.key}</span>
          <span className="font-mono text-xs text-fg-muted">{e.evidence_id}</span>
        </li>
      ))}
    </ul>
  );
}

function Paths({ result, graph }: { result: ToolResult; graph: ReturnType<typeof pathsToGraph> }) {
  if (result.paths.length === 0) {
    return (
      <EmptyState title="No paths traversed">
        Only tools that walk relationships return paths; this result has none.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-4">
      <EvidenceChain
        graph={graph}
        highlightIds={graph.nodes.map((n) => n.id)}
        label={`Subgraph traversed by the tool: ${graph.nodes.length} nodes and ${graph.edges.length} relations over ${result.paths.length} paths`}
        emptyText="The paths name no nodes."
      />
      <ol className="space-y-1 font-mono text-xs" aria-label="Paths as returned">
        {result.paths.map((p, i) => (
          <li key={i} className="break-all text-fg-secondary">
            {p.map((part, j) => (j % 2 === 1 ? ` —${part}— ` : part)).join("")}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Cypher({ name, params, template }: { name: string; params: Record<string, unknown>; template: string }) {
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();
  async function copy() {
    try {
      await navigator.clipboard.writeText(template);
      setCopied(true);
      toast("Cypher template copied");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="space-y-3">
      <div>
        <p className="text-xs text-fg-muted">
          Request: <span className="font-mono">POST /v1/tools/{name}</span>
        </p>
        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-surface-subtle p-2 font-mono text-xs">
          {JSON.stringify(params, null, 2)}
        </pre>
      </div>
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-fg-muted">Cypher template (read-only, parameterised; the values above are bound as parameters)</p>
          <button type="button" onClick={() => void copy()} className={cx("inline-flex h-7 items-center gap-1 rounded-sm border border-border-input px-2 text-sm")}>
            <Copy size={14} strokeWidth={1.5} aria-hidden="true" />
            {copied ? "Copied" : "Copy template"}
          </button>
        </div>
        {template ? (
          <pre className="mt-1 max-h-96 overflow-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-surface-subtle p-2 font-mono text-xs">
            {template}
          </pre>
        ) : (
          <p className="mt-1 text-sm text-fg-secondary">The tool reported no template: it is composed in code, not from one Cypher query.</p>
        )}
      </div>
    </div>
  );
}
