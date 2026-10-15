"use client";

import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useId, useMemo, useState, useSyncExternalStore } from "react";
import type { Finding, FindingsSummary, GraphOut } from "@/lib/api/types";
import { FINDING_KIND_TEXT, numberFromPath } from "@/lib/format";
import { kindLabel, kindTones, toneColor } from "@/lib/kinds";
import { GraphView, type NodeDecoration } from "./GraphView";
import { KepLink, SigLink, TableWrap, cx, tableClass, tdClass, thClass } from "./ui";

const KEP_ARC = 34;
const MIN_RING = 125;
const FINDING_GAP = 40;
const CLUSTER_GAP = 32;
const KEP_SIZE = 18;
const FINDING_SIZE = 14;
const SIG_SIZE = 40;
/** Approximate advance of an 11px monospace character, used to keep radial labels clear of their node. */
const CHAR_W = 6.6;

function subscribeWidth(cb: () => void) {
  const mq = window.matchMedia("(max-width: 767px)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
}

function sigOf(f: Finding): string {
  return f.owning_sig ?? f.kep_path.split("/")[1] ?? "unknown";
}

interface Built {
  graph: GraphOut;
  positions: Record<string, { x: number; y: number }>;
  decorations: Record<string, NodeDecoration>;
}

/**
 * One radial cluster per SIG: the SIG in the centre, its flagged KEPs on a ring (ordered by number),
 * each KEP's findings just outside it. Edges keep their stored direction: Finding -ABOUT-> KEP -OWNED_BY-> SIG.
 */
function build(items: Finding[], sigOrder: string[], tones: Map<string, number | null>): Built {
  const bySig = new Map<string, Map<string, Finding[]>>();
  for (const f of items) {
    const sig = sigOf(f);
    if (!bySig.has(sig)) bySig.set(sig, new Map());
    const keps = bySig.get(sig)!;
    if (!keps.has(f.kep_path)) keps.set(f.kep_path, []);
    keps.get(f.kep_path)!.push(f);
  }
  const sigs = [...sigOrder.filter((s) => bySig.has(s)), ...[...bySig.keys()].filter((s) => !sigOrder.includes(s)).sort()];

  const graph: GraphOut = { nodes: [], edges: [] };
  const positions: Built["positions"] = {};
  const decorations: Built["decorations"] = {};
  let left = 0;

  for (const sig of sigs) {
    const keps = [...bySig.get(sig)!.entries()].sort(
      (a, b) => (numberFromPath(a[0]) ?? 0) - (numberFromPath(b[0]) ?? 0) || a[0].localeCompare(b[0]),
    );
    const n = keps.length;
    const r1 = Math.max(MIN_RING, (n * KEP_ARC) / (2 * Math.PI));
    const r2 = r1 + FINDING_GAP;
    const radius = r2 + FINDING_SIZE;
    const cx0 = left + radius;
    left = cx0 + radius + CLUSTER_GAP;

    const sigId = `sig:${sig}`;
    graph.nodes.push({ id: sigId, label: "SIG", key: sig, title: `${sig}: ${n} KEP${n === 1 ? "" : "s"} with findings`, url: null });
    positions[sigId] = { x: cx0, y: 0 };
    decorations[sigId] = { size: SIG_SIZE, labelPlate: true };

    keps.forEach(([path, findings], i) => {
      const theta = -Math.PI / 2 + (2 * Math.PI * i) / n;
      const cos = Math.cos(theta);
      const sin = Math.sin(theta);
      const kepId = `kep:${path}`;
      const num = numberFromPath(path);
      const badge = num !== null ? `KEP-${num}` : (path.split("/").pop() ?? path);
      graph.nodes.push({ id: kepId, label: "KEP", key: path, title: findings[0].kep_title, url: null });
      graph.edges.push({ source: kepId, target: sigId, type: "OWNED_BY" });
      positions[kepId] = { x: cx0 + r1 * cos, y: r1 * sin };
      // The label runs along the spoke, inside the ring, reading outward on the right half and inward on the left.
      const d = KEP_SIZE / 2 + 6 + (badge.length * CHAR_W) / 2;
      decorations[kepId] = {
        size: KEP_SIZE,
        labelDx: -cos * d,
        labelDy: -sin * d,
        labelAngle: cos >= 0 ? theta : theta + Math.PI,
        labelPlate: true,
      };

      const step = (FINDING_SIZE + 4) / r2;
      findings.forEach((f, j) => {
        const a = theta + (j - (findings.length - 1) / 2) * step;
        graph.nodes.push({
          id: f.key,
          label: "Finding",
          key: f.key,
          title: `on ${badge}: ${f.a_label} ${f.a_value ?? "none"}; ${f.b_label} ${f.b_value ?? "none"}`,
          url: null,
        });
        graph.edges.push({ source: f.key, target: kepId, type: "ABOUT" });
        positions[f.key] = { x: cx0 + r2 * Math.cos(a), y: r2 * Math.sin(a) };
        decorations[f.key] = { size: FINDING_SIZE, label: false, tone: tones.get(f.kind) ?? undefined };
      });
    });
  }
  return { graph, positions, decorations };
}

/** The live map of disagreeing records: SIG -> KEP -> Finding, from GET /v1/findings. */
export function ContradictionMap({
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
  const router = useRouter();
  const descId = useId();
  const narrow = useSyncExternalStore(
    subscribeWidth,
    () => window.matchMedia("(max-width: 767px)").matches,
    () => false,
  );
  const [tableChoice, setTableChoice] = useState<boolean | null>(null);
  const tableOnly = tableChoice ?? narrow;

  const tones = useMemo(() => kindTones(Object.keys(summary.by_kind)), [summary]);
  const built = useMemo(() => build(items, sigOrder, tones), [items, sigOrder, tones]);
  const sigCount = new Set(items.map(sigOf)).size;
  const legend = Object.entries(summary.by_kind).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  function onSelect(key: string | null) {
    if (!key) return;
    if (key.startsWith("fnd:")) {
      router.push(`/audit?finding=${encodeURIComponent(key)}#findings` as Route);
      return;
    }
    const node = built.graph.nodes.find((n) => n.key === key);
    if (node?.label === "KEP") {
      const num = numberFromPath(key);
      if (num !== null) router.push(`/explore/kep/${num}` as Route);
    } else if (node?.label === "SIG") {
      router.push(`/explore/sig/${encodeURIComponent(key)}` as Route);
    }
  }

  return (
    <section aria-labelledby={`${descId}-t`} className="rounded-md border border-border bg-surface">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-4 py-3">
        <div>
          <h2 id={`${descId}-t`} className="text-md font-semibold">
            Where the records disagree
          </h2>
          <p className="text-sm text-fg-secondary">
            <span className="tabular">{summary.total.toLocaleString("en-US")}</span> findings on{" "}
            <span className="tabular">{summary.flagged_keps.toLocaleString("en-US")}</span> KEPs in {sigCount} SIG{sigCount === 1 ? "" : "s"}: kep.yaml,
            the tracking issue or a replacement declaration say different things
            {sha ? (
              <>
                {" "}
                at <span className="ident">{sha.slice(0, 7)}</span>
              </>
            ) : null}
            .
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <button
            type="button"
            aria-pressed={tableOnly}
            onClick={() => setTableChoice(!tableOnly)}
            className="h-7 rounded-sm border border-border-input px-2"
          >
            Table only
          </button>
          <Link href="/audit" className="quiet-link">
            Open Audit
          </Link>
        </div>
      </div>

      <ul aria-label="Finding kinds" className="flex flex-wrap gap-x-5 gap-y-1 border-b border-border px-4 py-2 text-sm">
        {legend.map(([kind, count]) => (
          <li key={kind}>
            <Link
              href={`/audit?kind=${encodeURIComponent(kind)}#findings` as Route}
              className="group inline-flex items-center gap-2"
              title={`${kind}: ${FINDING_KIND_TEXT[kind] ?? ""}`}
            >
              <span aria-hidden="true" className="inline-block h-3 w-3 shrink-0 rounded-sm" style={{ background: toneColor(tones.get(kind)) }} />
              <span className="text-fg group-hover:underline">{kindLabel(kind)}</span>
              <span className="tabular text-fg-secondary">{count.toLocaleString("en-US")}</span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="p-4">
        {tableOnly ? (
          <MapTable items={items} tones={tones} />
        ) : (
          <>
            <GraphView
              elements={built.graph}
              layout="preset"
              positions={built.positions}
              decorations={built.decorations}
              onSelect={onSelect}
              label={`Map of ${summary.total} findings on ${summary.flagged_keps} KEPs, grouped by owning SIG`}
              describedBy={`${descId}-d`}
              height={440}
            />
            <p id={`${descId}-d`} className="mt-1 text-xs text-fg-muted">
              Hexagon SIG, rounded rectangle KEP, filled marker finding coloured by kind. Edges in the stored direction:{" "}
              <span className="ident">Finding —ABOUT→ KEP —OWNED_BY→ SIG</span>. Click a KEP for its record, a finding for both sides in
              Audit, a SIG for its page.
            </p>
          </>
        )}
      </div>
    </section>
  );
}

function MapTable({ items, tones }: { items: Finding[]; tones: Map<string, number | null> }) {
  const rows = [...items].sort(
    (a, b) => sigOf(a).localeCompare(sigOf(b)) || (a.kep_number ?? 0) - (b.kep_number ?? 0) || a.kind.localeCompare(b.kind),
  );
  return (
    <div className="max-h-[460px] overflow-y-auto">
      <TableWrap label="Findings by KEP">
        <table className={tableClass}>
          <caption className="sr-only">Every finding with its KEP and SIG</caption>
          <thead className="sticky top-0">
            <tr>
              <th className={thClass}>SIG</th>
              <th className={thClass}>KEP</th>
              <th className={thClass}>Kind</th>
              <th className={cx(thClass, "hidden sm:table-cell")}>Records</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => {
              const tone = tones.get(f.kind) ?? null;
              return (
                <tr key={f.key}>
                  <td className={tdClass}>
                    <SigLink sig={sigOf(f)} />
                  </td>
                  <td className={cx(tdClass, "whitespace-nowrap")}>
                    <KepLink number={f.kep_number ?? numberFromPath(f.kep_path)} />
                  </td>
                  <td className={tdClass}>
                    <Link href={`/audit?finding=${encodeURIComponent(f.key)}#findings` as Route} className="quiet-link inline-flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                        style={{ background: toneColor(tone) }}
                      />
                      <span>{kindLabel(f.kind)}</span>
                    </Link>
                  </td>
                  <td className={cx(tdClass, "hidden text-xs text-fg-secondary sm:table-cell")}>
                    {f.a_label}: <span className="ident text-fg">{f.a_value ?? "none"}</span>; {f.b_label}:{" "}
                    <span className="ident text-fg">{f.b_value ?? "none"}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableWrap>
    </div>
  );
}
