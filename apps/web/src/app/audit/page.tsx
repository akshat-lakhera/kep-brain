import type { Metadata } from "next";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import type { FindingsResponse } from "@/lib/api/types";
import { FINDING_KIND_TEXT } from "@/lib/format";
import { FindingsTable } from "@/components/FindingsTable";
import { Card, ErrorState, PageHeader, SkeletonBlock, StatTile, cx, tableClass, tdClass, thClass } from "@/components/ui";

export const metadata: Metadata = { title: "Audit" };

type Search = { kind?: string; sig?: string; state?: string; finding?: string };

function one(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v || undefined;
}

export default function AuditPage(props: PageProps<"/audit">) {
  return (
    <>
      <PageHeader
        title="Audit"
        lead="KEPs whose kep.yaml, tracking issue or replacement declarations disagree. Each row shows both records with their source URLs."
      />
      <Suspense fallback={<AuditSkeleton />}>
        <AuditBody searchParams={props.searchParams} />
      </Suspense>
    </>
  );
}

function AuditSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid max-w-md grid-cols-2 gap-4">
        <div className="skeleton h-24" />
        <div className="skeleton h-24" />
      </div>
      <SkeletonBlock lines={8} label="Loading findings" />
    </div>
  );
}

async function AuditBody({ searchParams }: { searchParams: PageProps<"/audit">["searchParams"] }) {
  const sp = await searchParams;
  const filter: Search = {
    kind: one(sp.kind),
    sig: one(sp.sig),
    state: one(sp.state),
    finding: one(sp.finding),
  };
  // The unfiltered summary feeds the filter options; the filtered call feeds the table.
  const [all, filtered] = await Promise.all([
    serverApi.findings({}),
    filter.kind || filter.sig || filter.state
      ? serverApi.findings({ kind: filter.kind, sig: filter.sig, state: filter.state })
      : Promise.resolve(null),
  ]);
  if (!all.ok) return <ErrorState error={all.error} what="Findings" />;
  const view: FindingsResponse | null = filtered === null ? all.data : filtered.ok ? filtered.data : null;

  return (
    <div className="space-y-6">
      <Summary data={all.data} />
      <Filters data={all.data} filter={filter} />
      {filtered && !filtered.ok ? (
        <ErrorState error={filtered.error} what="Filtered findings" />
      ) : view ? (
        <FindingsTable items={view.items} selected={filter.finding} filtered={Boolean(filter.kind || filter.sig || filter.state)} />
      ) : null}
    </div>
  );
}

function Summary({ data }: { data: FindingsResponse }) {
  const kinds = Object.entries(data.summary.by_kind).sort((a, b) => b[1] - a[1]);
  const sigs = Object.entries(data.summary.by_sig).sort((a, b) => b[1] - a[1]);
  return (
    <section aria-label="Summary" className="space-y-4">
      <div className="grid max-w-md grid-cols-2 gap-4">
        <StatTile label="Findings" value={data.summary.total.toLocaleString("en-US")} />
        <StatTile label="KEPs flagged" value={data.summary.flagged_keps.toLocaleString("en-US")} />
      </div>
      <p className="text-sm text-fg-secondary">
        Recall is not measured: there is no complete list of disagreements to compare against.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="By kind">
          {kinds.length === 0 ? (
            <p className="text-fg-secondary">No findings.</p>
          ) : (
            <table className={tableClass}>
              <caption className="sr-only">Findings by kind</caption>
              <thead>
                <tr>
                  <th className={thClass}>Kind</th>
                  <th className={cx(thClass, "text-right")}>Findings</th>
                </tr>
              </thead>
              <tbody>
                {kinds.map(([k, v]) => (
                  <tr key={k}>
                    <td className={tdClass}>
                      <a href={`/audit?kind=${encodeURIComponent(k)}`} className="quiet-link font-mono">
                        {k}
                      </a>
                      {FINDING_KIND_TEXT[k] ? <p className="mt-0.5 text-xs text-fg-muted">{FINDING_KIND_TEXT[k]}</p> : null}
                    </td>
                    <td className={cx(tdClass, "tabular text-right")}>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card title="By SIG">
          {sigs.length === 0 ? (
            <p className="text-fg-secondary">No findings.</p>
          ) : (
            <table className={tableClass}>
              <caption className="sr-only">Findings by owning SIG</caption>
              <thead>
                <tr>
                  <th className={thClass}>SIG</th>
                  <th className={cx(thClass, "text-right")}>Findings</th>
                </tr>
              </thead>
              <tbody>
                {sigs.map(([k, v]) => (
                  <tr key={k}>
                    <td className={tdClass}>
                      <a href={`/audit?sig=${encodeURIComponent(k)}`} className="quiet-link font-mono">
                        {k}
                      </a>
                    </td>
                    <td className={cx(tdClass, "tabular text-right")}>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </section>
  );
}

function Filters({ data, filter }: { data: FindingsResponse; filter: Search }) {
  const kinds = Object.keys(data.summary.by_kind).sort();
  const sigs = Object.keys(data.summary.by_sig).sort();
  const states = Array.from(new Set(data.items.map((f) => f.state))).sort();
  const select = "h-8 rounded-sm border border-border-input bg-surface px-2 text-base";
  return (
    <form method="get" action="/audit" className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-surface p-3" aria-label="Filter findings">
      <label className="flex flex-col gap-1 text-sm text-fg-secondary">
        Kind
        <select name="kind" defaultValue={filter.kind ?? ""} className={select}>
          <option value="">All kinds</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm text-fg-secondary">
        SIG
        <select name="sig" defaultValue={filter.sig ?? ""} className={select}>
          <option value="">All SIGs</option>
          {sigs.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm text-fg-secondary">
        State
        <select name="state" defaultValue={filter.state ?? ""} className={select}>
          <option value="">All states</option>
          {states.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="h-8 rounded-sm bg-accent px-3 font-medium text-on-accent hover:bg-accent-hover">
        Apply
      </button>
      {filter.kind || filter.sig || filter.state ? (
        <a href="/audit" className="quiet-link h-8 leading-8">
          Clear filters
        </a>
      ) : null}
    </form>
  );
}
