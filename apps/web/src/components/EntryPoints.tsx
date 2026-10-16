import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";
import type { ApiResult } from "@/lib/api/core";
import { routes } from "@/lib/routes";
import type { ChangesResponse, Finding, FindingsSummary, SigSummary } from "@/lib/api/types";
import { isoDate, numberFromPath } from "@/lib/format";
import { kindLabel } from "@/lib/kinds";
import { Dash, ErrorState, KepLink, SigLink } from "./ui";

const ROWS = 7;

function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="min-w-0 bg-surface p-4" aria-label={title}>
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function sigItems(res: ApiResult<{ items: SigSummary[] } | SigSummary[]>): SigSummary[] | null {
  if (!res.ok) return null;
  const list = Array.isArray(res.data) ? res.data : res.data.items;
  return Array.isArray(list) ? list.filter((s) => typeof s?.key === "string") : null;
}

/** Where to start, from the data itself: recent changes, the SIGs, and the open findings. */
export function EntryPoints({
  changes,
  sigs,
  metaSigs,
  findings,
  summary,
}: {
  changes: ApiResult<ChangesResponse>;
  sigs: ApiResult<{ items: SigSummary[] } | SigSummary[]>;
  metaSigs: string[];
  findings: Finding[];
  summary: FindingsSummary | null;
}) {
  const sigList = sigItems(sigs);
  // Only the SIGs whose KEPs are loaded; the rest of sigs.yaml has no KEP data behind it.
  const loaded = new Set(metaSigs);
  const teams: SigSummary[] = sigList
    ? sigList.filter((s) => loaded.has(s.key))
    : metaSigs.map((key) => ({ key }));
  const open = findings.filter((f) => f.state === "open");
  const byKep = new Map<string, Finding[]>();
  for (const f of open) byKep.set(f.kep_path, [...(byKep.get(f.kep_path) ?? []), f]);
  const topKeps = [...byKep.entries()]
    .sort((a, b) => b[1].length - a[1].length || (numberFromPath(a[0]) ?? 0) - (numberFromPath(b[0]) ?? 0))
    .slice(0, ROWS);

  return (
    <div className="grid gap-px overflow-hidden rounded-md border border-border bg-border md:grid-cols-3">
      <Panel title="Changed most recently">
        <RecentChanges changes={changes} />
      </Panel>

      <Panel title="SIGs">
        {teams.length === 0 ? (
          <p className="text-sm text-fg-secondary">The API reports no loaded SIG.</p>
        ) : (
          <table className="w-full text-sm">
            <caption className="sr-only">Loaded SIGs with their KEPs and findings</caption>
            <thead>
              <tr className="text-xs text-fg-secondary">
                <th className="py-1 text-left font-normal">SIG</th>
                {sigList?.some((s) => typeof s.keps === "number") ? <th className="py-1 text-right font-normal">KEPs</th> : null}
                <th className="py-1 text-right font-normal">Findings</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((s) => {
                const count = s.open_findings ?? s.findings ?? summary?.by_sig[s.key] ?? 0;
                return (
                  <tr key={s.key} className="border-t border-border">
                    <td className="py-1.5">
                      <SigLink sig={s.key} />
                      {s.display_name ? <span className="block text-xs text-fg-muted">{s.display_name}</span> : null}
                    </td>
                    {sigList?.some((x) => typeof x.keps === "number") ? (
                      <td className="tabular py-1.5 text-right">{typeof s.keps === "number" ? s.keps.toLocaleString("en-US") : <Dash />}</td>
                    ) : null}
                    <td className="py-1.5 text-right">
                      {count === 0 ? (
                        <span className="tabular text-fg-muted">0</span>
                      ) : (
                        <Link href={routes.auditSig(s.key)} className="quiet-link tabular" aria-label={`${count} findings in ${s.key}`}>
                          {count.toLocaleString("en-US")}
                        </Link>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel
        title={`Open findings · ${open.length.toLocaleString("en-US")}`}
        action={
          <Link href={"/audit?state=open#findings" as Route} className="quiet-link text-xs">
            All in Audit
          </Link>
        }
      >
        {topKeps.length === 0 ? (
          <p className="text-sm text-fg-secondary">No finding is open.</p>
        ) : (
          <ul className="text-sm">
            {topKeps.map(([path, fs]) => (
              <li key={path} className="flex items-baseline gap-2 border-t border-border py-1.5 first:border-t-0">
                <KepLink number={fs[0].kep_number ?? numberFromPath(path)} />
                <span className="min-w-0 flex-1 truncate" title={fs[0].kep_title ?? undefined}>
                  {fs[0].kep_title}
                </span>
                <Link
                  href={routes.finding(fs[0].key)}
                  className="quiet-link shrink-0 text-xs"
                  title={fs.map((f) => kindLabel(f.kind)).join(", ")}
                >
                  {fs.length === 1 ? kindLabel(fs[0].kind) : `${fs.length} findings`}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function RecentChanges({ changes }: { changes: ApiResult<ChangesResponse> }) {
  if (!changes.ok) {
    if (changes.error.status === 404) {
      return (
        <p className="text-sm text-fg-secondary">
          The change log is not served by this API yet (<span className="ident">GET /v1/changes</span> answered 404).
        </p>
      );
    }
    return <ErrorState error={changes.error} what="Recent changes" />;
  }
  const seen = new Set<string>();
  const rows = [...changes.data.items]
    .sort((a, b) => (b.at_iso ?? "").localeCompare(a.at_iso ?? ""))
    .filter((c) => {
      const k = String(c.kep_number ?? c.kep_title);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .slice(0, ROWS);
  if (rows.length === 0) {
    return (
      <p className="text-sm text-fg-secondary">
        No status, stage or milestone change{changes.data.since ? ` since ${changes.data.since}` : ""}.
      </p>
    );
  }
  return (
    <ul className="text-sm">
      {rows.map((c, i) => (
        <li key={`${c.kep_number}-${i}`} className="border-t border-border py-1.5 first:border-t-0">
          <span className="flex items-baseline gap-2">
            <KepLink number={c.kep_number} />
            <span className="min-w-0 flex-1 truncate" title={c.kep_title ?? undefined}>
              {c.kep_title}
            </span>
            <span className="ident shrink-0 text-xs text-fg-muted">{isoDate(c.at_iso)}</span>
          </span>
          <span className="block text-xs text-fg-secondary">{describeChange(c)}</span>
        </li>
      ))}
    </ul>
  );
}

/** One plain sentence per change: label added/removed, or field set/changed/cleared. */
function describeChange(c: ChangesResponse["items"][number]): string {
  if (c.kind === "label") return c.to_value ? `Label ${c.field} added` : `Label ${c.field} removed`;
  const field = c.field.replace(/_/g, " ");
  if (!c.from_value) return `${field} set to ${c.to_value}`;
  if (!c.to_value) return `${field} cleared (was ${c.from_value})`;
  return `${field} ${c.from_value} → ${c.to_value}`;
}
