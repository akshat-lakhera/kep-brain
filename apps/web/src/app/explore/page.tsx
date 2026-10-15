import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";
import { apiInternalUrl, serverApi } from "@/lib/api/server";
import { exploreApi, explorePaths, isNotFound } from "@/lib/api/explore";
import type { ApiResult } from "@/lib/api/core";
import type { Finding, FindingsResponse } from "@/lib/api/types";
import type { ChangesOut, SigCard } from "@/lib/api/types-explore";
import { isoUtc } from "@/lib/format";
import { Card, Dash, EmptyState, ErrorState, ExtLink, KepLink, PageHeader, SkeletonBlock, TableWrap, cx, tableClass, tdClass, thClass } from "@/components/ui";
import { ExploreSearch } from "@/components/explore/ExploreSearch";
import { PersonLink, SigLink } from "@/components/explore/links";

export const metadata: Metadata = { title: "Explore" };

export default function ExplorePage(props: PageProps<"/explore">) {
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <div className="skeleton h-8 w-1/3" />
          <SkeletonBlock lines={6} label="Loading the index" />
        </div>
      }
    >
      <ExploreBody searchParams={props.searchParams} />
    </Suspense>
  );
}

async function ExploreBody({ searchParams }: { searchParams: PageProps<"/explore">["searchParams"] }) {
  await connection();
  const sp = await searchParams;
  const since = typeof sp.since === "string" ? sp.since : undefined;
  const api = exploreApi(apiInternalUrl());
  const [meta, sigs, findings, changes] = await Promise.all([
    serverApi.meta(),
    api.sigs(),
    serverApi.findings({ state: "open" }),
    api.changes({ since }),
  ]);
  const loadedSigs = meta.ok ? meta.data.sigs : [];
  const sigItems: { key: string; display_name: string | null }[] = sigs.ok
    ? sigs.data.items.map((s) => ({ key: s.key, display_name: s.display_name }))
    : loadedSigs.map((key) => ({ key, display_name: null }));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Explore"
        lead={
          meta.ok ? (
            <>
              {meta.data.graph.keps.toLocaleString("en-US")} KEPs, {meta.data.graph.people.toLocaleString("en-US")} people and{" "}
              {meta.data.graph.findings.toLocaleString("en-US")} findings across{" "}
              <span className="font-mono">{meta.data.sigs.join(", ")}</span>: who owns what, who decided each state, and what is unresolved.
            </>
          ) : (
            "Who owns what, who decided each state, and what is unresolved."
          )
        }
      />
      <ExploreSearch sigs={sigItems} />
      {!meta.ok ? <ErrorState error={meta.error} what="Graph summary" /> : null}
      <SigStrip result={sigs} loadedSigs={loadedSigs} />
      <div className="space-y-6">
        <Card title="KEPs with open findings" id="open-findings">
          <OpenFindings result={findings} />
        </Card>
        <Card title="Recently changed" id="changes">
          <Changes result={changes} since={since} />
        </Card>
      </div>
    </div>
  );
}

function SigStrip({ result, loadedSigs }: { result: ApiResult<{ items: SigCard[] }>; loadedSigs: string[] }) {
  if (!result.ok) {
    if (isNotFound(result.error))
      return (
        <EmptyState title="SIG summaries are not available yet">
          The API does not answer <span className="font-mono">GET {explorePaths.sigs()}</span>.{" "}
          {loadedSigs.length ? (
            <>
              Loaded SIGs from <span className="font-mono">/v1/meta</span>:{" "}
              <span className="flex flex-wrap gap-x-3">
                {loadedSigs.map((s) => (
                  <SigLink key={s} sig={s} />
                ))}
              </span>
            </>
          ) : (
            "The API did not report which SIGs are loaded."
          )}
        </EmptyState>
      );
    return <ErrorState error={result.error} what="SIGs" />;
  }
  const items = result.data.items;
  if (items.length === 0) return <EmptyState title="No SIG loaded">The API lists no SIG; nothing from sigs.yaml has been read yet.</EmptyState>;
  return (
    <section aria-label="SIGs" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((s) => (
        <div key={s.key} className="rounded-md border border-border bg-surface p-3">
          <p className="flex flex-wrap items-baseline gap-x-2">
            <SigLink sig={s.key} className="quiet-link font-mono font-medium" />
            {s.display_name && s.display_name !== s.key ? <span className="text-sm text-fg-secondary">{s.display_name}</span> : null}
            {!s.in_scope ? <span className="text-xs text-fg-muted">not loaded</span> : null}
          </p>
          <p className="mt-1 text-sm">
            <span className="tabular">{s.keps.toLocaleString("en-US")}</span> KEPs ·{" "}
            <span className="tabular">{s.open_findings.toLocaleString("en-US")}</span> open finding{s.open_findings === 1 ? "" : "s"}
          </p>
          <p className="mt-1 text-sm text-fg-secondary">
            Chairs:{" "}
            {s.chairs.length ? (
              <span className="inline-flex flex-wrap gap-x-2">
                {s.chairs.map((p) => (
                  <PersonLink key={p.login} login={p.login} />
                ))}
              </span>
            ) : (
              <Dash />
            )}
          </p>
        </div>
      ))}
    </section>
  );
}

function OpenFindings({ result }: { result: ApiResult<FindingsResponse> }) {
  if (!result.ok) return <ErrorState error={result.error} what="Findings" />;
  const byKep = new Map<string, { number: number | null; title: string | null; sig: string | null; kinds: string[]; first: Finding }>();
  for (const f of result.data.items) {
    const cur = byKep.get(f.kep_path);
    if (cur) cur.kinds.push(f.kind);
    else byKep.set(f.kep_path, { number: f.kep_number, title: f.kep_title, sig: f.owning_sig, kinds: [f.kind], first: f });
  }
  const rows = Array.from(byKep.entries()).sort((a, b) => b[1].kinds.length - a[1].kinds.length || (a[1].number ?? 0) - (b[1].number ?? 0));
  if (rows.length === 0)
    return <EmptyState title="No open findings">Every finding in the graph is closed or triaged; the detector found no open disagreement.</EmptyState>;
  return (
    <TableWrap label="KEPs with open findings">
      <table className={tableClass}>
        <caption className="mb-1 text-left text-xs text-fg-muted">
          {rows.length.toLocaleString("en-US")} KEPs with {result.data.items.length.toLocaleString("en-US")} open findings, most findings first.{" "}
          <Link href={"/audit" as Route} className="quiet-link">
            Open the audit
          </Link>
        </caption>
        <thead>
          <tr>
            <th className={thClass}>KEP</th>
            <th className={thClass}>Title</th>
            <th className={thClass}>SIG</th>
            <th className={thClass}>Findings</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([path, r]) => (
            <tr key={path}>
              <td className={cx(tdClass, "whitespace-nowrap")}>
                <KepLink number={r.number} label={r.number !== null ? undefined : path} />
              </td>
              <td className={tdClass}>{r.title ?? <Dash />}</td>
              <td className={tdClass}>{r.sig ? <SigLink sig={r.sig} /> : <Dash />}</td>
              <td className={tdClass}>
                <span className="tabular">{r.kinds.length}</span>
                {r.kinds.map((k, i) => (
                  <Link
                    key={`${k}-${i}`}
                    href={`/audit?finding=${encodeURIComponent(r.first.key)}` as Route}
                    className="quiet-link ml-2 font-mono text-xs"
                  >
                    {k}
                  </Link>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

function Changes({ result, since }: { result: ApiResult<ChangesOut>; since?: string }) {
  if (!result.ok) {
    if (isNotFound(result.error))
      return (
        <EmptyState title="Recent changes are not available yet">
          The API does not answer <span className="font-mono">GET {explorePaths.changes({ since })}</span>. Until it does, each KEP page&apos;s Status
          history tab lists that KEP&apos;s changes.
        </EmptyState>
      );
    return <ErrorState error={result.error} what="Recent changes" />;
  }
  const d = result.data;
  const counts = Object.entries(d.counts);
  return (
    <div className="space-y-3">
      <p className="text-sm text-fg-secondary">
        {d.since ? (
          <>
            Since <span className="font-mono">{d.since}</span>
          </>
        ) : (
          "Most recent changes"
        )}
        {counts.length ? (
          <>
            {" "}
            ·{" "}
            {counts.map(([k, v], i) => (
              <span key={k}>
                {i > 0 ? ", " : ""}
                <span className="tabular">{v.toLocaleString("en-US")}</span> <span className="font-mono">{k}</span>
              </span>
            ))}
          </>
        ) : null}
      </p>
      {d.releases.length ? (
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-fg-secondary">Releases:</span>
          {d.releases.map((r) => (
            <Link
              key={r}
              href={`/explore?since=${encodeURIComponent(r)}#changes` as Route}
              className={cx("quiet-link rounded-sm border px-1.5 font-mono text-xs", r === d.since ? "border-accent" : "border-border")}
              aria-current={r === d.since ? "true" : undefined}
            >
              {r}
            </Link>
          ))}
        </p>
      ) : null}
      {d.items.length === 0 ? (
        <EmptyState title="No change in this window">
          No status, stage or milestone change was recorded {d.since ? `since ${d.since}` : "recently"}.
        </EmptyState>
      ) : (
        <TableWrap label="Recently changed KEPs">
          <table className={tableClass}>
            <thead>
              <tr>
                <th className={thClass}>At</th>
                <th className={thClass}>KEP</th>
                <th className={thClass}>Change</th>
                <th className={thClass}>Actor</th>
                <th className={thClass}>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((c, i) => (
                <tr key={`${c.kep_number}-${c.field}-${c.at_iso}-${i}`}>
                  <td className={cx(tdClass, "whitespace-nowrap font-mono text-xs")}>{isoUtc(c.at_iso) || <Dash />}</td>
                  <td className={cx(tdClass, "min-w-48")}>
                    <KepLink number={c.kep_number} /> <span className="text-sm">{c.kep_title}</span>
                    {c.owning_sig ? (
                      <span className="block text-xs">
                        <SigLink sig={c.owning_sig} />
                      </span>
                    ) : null}
                  </td>
                  <td className={cx(tdClass, "font-mono text-xs")}>
                    <span className="text-fg-muted">{c.field}</span> {c.from_value ?? "∅"} → {c.to_value ?? "∅"}
                  </td>
                  <td className={tdClass}>{c.actor_login ? <PersonLink login={c.actor_login} /> : <Dash />}</td>
                  <td className={cx(tdClass, "whitespace-nowrap")}>
                    {c.pr ? (
                      <ExtLink href={c.pr.url}>
                        <span className="font-mono">PR #{c.pr.number}</span>
                      </ExtLink>
                    ) : c.source_url ? (
                      <ExtLink href={c.source_url}>source</ExtLink>
                    ) : (
                      <Dash />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </div>
  );
}
