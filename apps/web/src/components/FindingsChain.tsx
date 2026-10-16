"use client";

import Link from "next/link";
import { useId, useMemo } from "react";
import type { Finding, FindingsSummary, GraphOut } from "@/lib/api/types";
import { routes } from "@/lib/routes";
import { FINDING_KIND_TEXT, numberFromPath, pluralS } from "@/lib/format";
import { kindLabel } from "@/lib/kinds";
import { EvidenceChain } from "./EvidenceChain";

function sigOf(f: Finding): string {
  return f.owning_sig ?? f.kep_path.split("/")[1] ?? "unknown";
}

/** SIG -> KEP -> Finding as a graph, in the stored direction: Finding -ABOUT-> KEP -OWNED_BY-> SIG. */
function build(items: Finding[], sigOrder: string[]): { graph: GraphOut; roots: string[] } {
  const graph: GraphOut = { nodes: [], edges: [] };
  const sigs = new Set<string>();
  const keps = new Set<string>();
  for (const f of items) {
    const sig = sigOf(f);
    const sigId = `sig:${sig}`;
    if (!sigs.has(sig)) {
      sigs.add(sig);
      graph.nodes.push({ id: sigId, label: "SIG", key: sig, title: null, url: null });
    }
    const kepId = `kep:${f.kep_path}`;
    if (!keps.has(f.kep_path)) {
      keps.add(f.kep_path);
      graph.nodes.push({ id: kepId, label: "KEP", key: f.kep_path, title: f.kep_title, url: null });
      graph.edges.push({ source: kepId, target: sigId, type: "OWNED_BY" });
    }
    graph.nodes.push({
      id: f.key,
      label: "Finding",
      key: f.key,
      title: `${kindLabel(f.kind)}: ${f.a_label} ${f.a_value ?? "none"}; ${f.b_label} ${f.b_value ?? "none"}`,
      url: null,
    });
    graph.edges.push({ source: f.key, target: kepId, type: "ABOUT" });
  }
  const ordered = [...sigOrder.filter((s) => sigs.has(s)), ...[...sigs].filter((s) => !sigOrder.includes(s)).sort()];
  return { graph, roots: ordered.map((s) => `sig:${s}`) };
}

/** Where the records disagree: every finding under its KEP under its SIG, as an evidence chain. */
export function FindingsChain({
  items,
  summary,
  sigOrder,
  sha,
}: {
  items: Finding[];
  summary: FindingsSummary;
  sigOrder: string[];
  sha: string | null;
}) {
  const id = useId();
  const built = useMemo(() => build(items, sigOrder), [items, sigOrder]);
  const sigCount = built.roots.length;
  const legend = Object.entries(summary.by_kind).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const kepCount = new Set(items.map((f) => numberFromPath(f.kep_path) ?? f.kep_path)).size;

  return (
    <section aria-labelledby={`${id}-t`} className="rounded-md border border-border bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-4 py-3">
        <div>
          <h2 id={`${id}-t`} className="text-md font-semibold">
            Where the records disagree
          </h2>
          <p className="text-sm text-fg-secondary">
            <span className="tabular">{summary.total.toLocaleString("en-US")}</span> findings on{" "}
            <span className="tabular">{kepCount.toLocaleString("en-US")}</span> KEPs in {sigCount} SIG{pluralS(sigCount)}: kep.yaml, the
            tracking issue or a replacement declaration say different things
            {sha ? (
              <>
                {" "}
                at <span className="ident">{sha.slice(0, 7)}</span>
              </>
            ) : null}
            .
          </p>
        </div>
        <Link href="/audit" className="quiet-link text-sm">
          Open Audit
        </Link>
      </div>
      <ul aria-label="Finding kinds" className="flex flex-wrap gap-x-5 gap-y-1 border-b border-border px-4 py-2 text-sm">
        {legend.map(([kind, count]) => (
          <li key={kind}>
            <Link href={routes.auditKind(kind)} className="group inline-flex items-center gap-2" title={FINDING_KIND_TEXT[kind] ?? kind}>
              <span className="text-fg group-hover:underline">{kindLabel(kind)}</span>
              <span className="tabular text-fg-secondary">{count.toLocaleString("en-US")}</span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="p-4">
        <EvidenceChain
          graph={built.graph}
          rootIds={built.roots}
          label={`${summary.total} findings on ${kepCount} KEPs, grouped by owning SIG`}
          emptyText="No finding to show."
          expandable={false}
        />
      </div>
    </section>
  );
}
