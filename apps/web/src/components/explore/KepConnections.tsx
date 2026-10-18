"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { clientApi } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/core";
import type { Evidence, ToolResult } from "@/lib/api/types";
import { numberFromPath } from "@/lib/format";
import { pageHref } from "@/lib/routes";
import { EmptyState, ErrorState, ExtLink, SkeletonBlock } from "@/components/ui";

const PATH_TOOL = "path_between";

/** One entity already shown on the KEP page that a path can end at. */
export interface ConnectTarget {
  label: "Person" | "SIG";
  key: string;
  /** What the option says, e.g. "@login (author, approver)". */
  text: string;
}

interface Hop {
  rel: string;
  /** True when the stored edge points from the node before the hop to the node after it. */
  forward: boolean;
}

interface PathRow {
  nodes: string[];
  hops: Hop[];
}

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; error: ApiFailure }
  | { kind: "done"; paths: PathRow[]; nodes: Map<string, Evidence>; within: number | null; timedOutAt: number | null };

/** Reads `path_between` rows into node and hop lists, dropping repeated paths. */
function readPaths(result: ToolResult): { paths: PathRow[]; within: number | null; timedOutAt: number | null } {
  const seen = new Set<string>();
  const paths: PathRow[] = [];
  let within: number | null = null;
  let timedOutAt: number | null = null;
  for (const row of result.rows) {
    if (typeof row.not_connected_within === "number") within = row.not_connected_within;
    if (typeof row.search_timed_out_at === "number") timedOutAt = row.search_timed_out_at;
    const raw = row.path;
    if (!Array.isArray(raw) || raw.length < 3) continue;
    const parts = raw.map(String);
    const id = parts.join("\u0000");
    if (seen.has(id)) continue;
    seen.add(id);
    const nodes = parts.filter((_, i) => i % 2 === 0);
    const edges = Array.isArray(row.edges) ? (row.edges as { from?: unknown; to?: unknown }[]) : [];
    const hops = parts
      .filter((_, i) => i % 2 === 1)
      .map((rel, i) => {
        const e = edges[i];
        return { rel, forward: e ? String(e.from) === nodes[i] : true };
      });
    paths.push({ nodes, hops });
  }
  return { paths, within, timedOutAt };
}

function NodeRef({ k, ev, self }: { k: string; ev: Evidence | undefined; self: string }) {
  const label = ev?.label ?? "";
  const cls = "ident inline-flex min-h-6 items-center";
  let text = ev?.title ?? k;
  if (label === "KEP") {
    const n = numberFromPath(k);
    if (n !== null) text = `KEP-${n}`;
  } else if (label === "Person") text = `@${k}`;
  else if (label === "SIG") text = k;
  if (k === self) return <span className={`${cls} font-semibold`}>{text}</span>;
  const href = pageHref({ id: k, key: k, label, title: ev?.title ?? null, url: ev?.url ?? null });
  if (href)
    return (
      <Link href={href} className={`quiet-link ${cls}`}>
        {text}
      </Link>
    );
  if (ev?.url)
    return (
      <ExtLink href={ev.url} className={cls}>
        {text}
      </ExtLink>
    );
  return <span className={cls}>{text}</span>;
}

/** Shortest graph paths between this KEP and a person or SIG picked from the page. */
export function KepConnections({ kepKey, targets }: { kepKey: string; targets: ConnectTarget[] }) {
  const id = useId();
  const [choice, setChoice] = useState(0);
  const [state, setState] = useState<State>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const target = targets[choice];

  async function run() {
    if (!target) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState({ kind: "loading" });
    const res = await clientApi.runTool(
      PATH_TOOL,
      { from_label: "KEP", from_key: kepKey, to_label: target.label, to_key: target.key, max_len: 4, path_count: 3 },
      ctrl.signal,
    );
    if (ctrl.signal.aborted) return;
    if (!res.ok) {
      setState({ kind: "error", error: res.error });
      return;
    }
    const nodes = new Map<string, Evidence>();
    for (const e of res.data.evidence) if (!nodes.has(e.key)) nodes.set(e.key, e);
    setState({ kind: "done", nodes, ...readPaths(res.data) });
  }

  if (!target) return <EmptyState title="Nothing to connect to">This KEP lists no owning SIG or people.</EmptyState>;

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-center gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <label htmlFor={`${id}-to`} className="text-fg-secondary">
          Connect this KEP to
        </label>
        <select
          id={`${id}-to`}
          value={choice}
          onChange={(e) => {
            setChoice(Number(e.target.value));
            setState({ kind: "idle" });
          }}
          className="h-9 rounded-sm border border-border-input bg-surface px-2 font-mono text-xs text-fg"
        >
          {targets.map((t, i) => (
            <option key={`${t.label}:${t.key}`} value={i}>
              {t.text}
            </option>
          ))}
        </select>
        <button type="submit" className="btn btn-secondary btn-sm" disabled={state.kind === "loading"}>
          Show paths
        </button>
      </form>
      <div aria-live="polite">
        {state.kind === "loading" ? <SkeletonBlock lines={3} label="Finding paths" /> : null}
        {state.kind === "error" ? <ErrorState error={state.error} what="Paths" /> : null}
        {state.kind === "done" && state.paths.length === 0 ? (
          <EmptyState title="No path found">
            {state.timedOutAt !== null
              ? `The search stopped at ${state.timedOutAt} hops because it took too long.`
              : `No connection within ${state.within ?? 4} hops, leaving out bots and release or label hubs.`}
          </EmptyState>
        ) : null}
        {state.kind === "done" && state.paths.length > 0 ? (
          <ol className="space-y-2">
            {state.paths.map((p) => (
              <li
                key={p.nodes.join("|") + p.hops.map((h) => h.rel).join("|")}
                className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border bg-surface-subtle px-3 py-2 text-sm"
              >
                <span className="sr-only">{`${p.hops.length} hop${p.hops.length === 1 ? "" : "s"}: `}</span>
                {p.nodes.map((k, i) => (
                  <span key={`${k}-${i}`} className="contents">
                    <NodeRef k={k} ev={state.nodes.get(k)} self={kepKey} />
                    {p.hops[i] ? (
                      <span className="font-mono text-xs text-fg-muted">
                        {p.hops[i].forward ? `—${p.hops[i].rel}→` : `←${p.hops[i].rel}—`}
                      </span>
                    ) : null}
                  </span>
                ))}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    </div>
  );
}
