import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";
import { apiInternalUrl, serverApi } from "@/lib/api/server";
import { exploreApi, explorePaths, isNotFound } from "@/lib/api/explore";
import type { ApiResult } from "@/lib/api/core";
import type { ChangesResponse, Finding, FindingsResponse } from "@/lib/api/types";
import type { SigCard } from "@/lib/api/types-explore";
import { isoUtc, plural, pluralS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { Card, Dash, EmptyState, ErrorState, ExtLink, KepLink, PageHeader, PersonLink, SigLink, SkeletonBlock, TableWrap, cx, tableClass, tdClass, thClass } from "@/components/ui";
import { ExploreSearch } from "@/components/explore/ExploreSearch";
import { ReleaseSelect } from "@/components/ReleaseSelect";
import { RowsPerPage } from "@/components/explore/RowsPerPage";
import { ROWS_DEFAULT, parseRows } from "@/lib/rows";

export const metadata: Metadata = {
  title: "Explore",
  description: "Search Kubernetes KEPs by number or title, browse SIGs and the people who author, review and approve them.",
  alternates: { canonical: "/explore" },
};

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
  const rows = parseRows(sp.rows);
  const page = pageOf(sp.page);
  const changeRows = parseRows(sp.crows);
  const changePage = pageOf(sp.cpage);
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
        <Card title="KEPs with open findings" id="open-findings" actions={<RowsPerPage value={rows} />}>
          <OpenFindings result={findings} rows={rows} page={page} since={since} />
        </Card>
        <Card title="Recently changed" id="changes" actions={<RowsPerPage value={changeRows} param="crows" pageParam="cpage" />}>
          <Changes result={changes} since={since} rows={changeRows} page={changePage} />
        </Card>
      </div>
    </div>
  );
}

function pageOf(raw: string | string[] | undefined): number {
  return Math.max(1, Number.parseInt(typeof raw === "string" ? raw : "", 10) || 1);
}

/** Slice a list for the current page; `rows` is the per-page choice from the URL. */
function paginate<T>(items: T[], rows: number | "all", page: number) {
  const size = rows === "all" ? Math.max(1, items.length) : rows;
  const pages = Math.max(1, Math.ceil(items.length / size));
  const current = Math.min(page, pages);
  const start = (current - 1) * size;
  return { shown: items.slice(start, start + size), start, pages, current, total: items.length };
}

/** "Showing a–b of N · Previous · Next" for a server-rendered table; `href` builds the link for a page number. */
function Pager({ slice, href }: { slice: ReturnType<typeof paginate<unknown>>; href: (page: number) => Route }) {
  const { shown, start, pages, current, total } = slice;
  return (
    <span className="tabular">
      Showing {(start + 1).toLocaleString("en-US")}–{(start + shown.length).toLocaleString("en-US")} of {total.toLocaleString("en-US")}
      {pages > 1 ? (
        <>
          {" · "}
          {current > 1 ? (
            <Link href={href(current - 1)} className="quiet-link">
              Previous
            </Link>
          ) : (
            <span className="text-fg-muted">Previous</span>
          )}
          {" · "}
          {current < pages ? (
            <Link href={href(current + 1)} className="quiet-link">
              Next
            </Link>
          ) : (
            <span className="text-fg-muted">Next</span>
          )}
        </>
      ) : null}
    </span>
  );
}

/** Build an /explore link that keeps the given query values and lands on a card. */
function exploreHref(values: Record<string, string | number | undefined>, anchor: string): Route {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) if (v !== undefined && v !== "") sp.set(k, String(v));
  const qs = sp.toString();
  return `/explore${qs ? `?${qs}` : ""}#${anchor}` as Route;
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
  const loaded = items.filter((s) => s.in_scope);
  const rest = items.filter((s) => !s.in_scope);
  return (
    <section aria-label="SIGs" className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {loaded.map((s) => (
          <SigTile key={s.key} s={s} />
        ))}
      </div>
      {rest.length > 0 ? (
        <details className="group">
          <summary className="cursor-pointer text-sm text-fg-secondary hover:text-fg">
            {plural(rest.length, "more SIG")} not loaded in this instance
          </summary>
          <p className="mt-2 text-xs text-fg-muted">
            These SIGs come from sigs.yaml; their KEPs are not loaded, so the counts below only reflect KEPs that list them as a
            participating SIG.
          </p>
          <div className="reveal mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {rest.map((s) => (
              <SigTile key={s.key} s={s} />
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function SigTile({ s }: { s: SigCard }) {
  return (
    <div className="rounded-md border border-border bg-surface p-3">
      <p className="flex flex-wrap items-baseline gap-x-2">
        <SigLink sig={s.key} className="quiet-link font-mono font-medium" />
        {s.display_name && s.display_name !== s.key ? <span className="text-sm text-fg-secondary">{s.display_name}</span> : null}
        {!s.in_scope ? <span className="text-xs text-fg-muted">not loaded</span> : null}
      </p>
      <p className="mt-1 text-sm">
        <span className="tabular">{s.keps.toLocaleString("en-US")}</span> KEP{pluralS(s.keps)} ·{" "}
        <span className="tabular">{s.open_findings.toLocaleString("en-US")}</span> open finding{pluralS(s.open_findings)}
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
  );
}

function OpenFindings({
  result,
  rows: perPage,
  page,
  since,
}: {
  result: ApiResult<FindingsResponse>;
  rows: number | "all";
  page: number;
  since?: string;
}) {
  if (!result.ok) return <ErrorState error={result.error} what="Findings" />;
  const byKep = new Map<string, { number: number | null; title: string | null; sig: string | null; findings: Finding[] }>();
  for (const f of result.data.items) {
    const cur = byKep.get(f.kep_path);
    if (cur) cur.findings.push(f);
    else byKep.set(f.kep_path, { number: f.kep_number, title: f.kep_title, sig: f.owning_sig, findings: [f] });
  }
  const rows = Array.from(byKep.entries()).sort((a, b) => b[1].findings.length - a[1].findings.length || (a[1].number ?? 0) - (b[1].number ?? 0));
  if (rows.length === 0)
    return <EmptyState title="No open findings">Every finding in the graph is closed or triaged; the detector found no open disagreement.</EmptyState>;
  const slice = paginate(rows, perPage, page);
  const pageHref = (p: number) =>
    exploreHref({ since, rows: perPage === ROWS_DEFAULT ? undefined : perPage, page: p > 1 ? p : undefined }, "open-findings");
  return (
    <TableWrap label="KEPs with open findings">
      <table className={tableClass}>
        <caption className="mb-1 text-left text-xs text-fg-muted">
          <span className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <span>
              {plural(rows.length, "KEP")} with {plural(result.data.items.length, "open finding")}, most findings first.{" "}
              <Link href={"/audit" as Route} className="quiet-link">
                Open the audit
              </Link>
            </span>
            <Pager slice={slice} href={pageHref} />
          </span>
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
          {slice.shown.map(([path, r]) => (
            <tr key={path}>
              <td className={cx(tdClass, "whitespace-nowrap")}>
                <KepLink number={r.number} label={r.number !== null ? undefined : path} />
              </td>
              <td className={tdClass}>{r.title ?? <Dash />}</td>
              <td className={tdClass}>{r.sig ? <SigLink sig={r.sig} /> : <Dash />}</td>
              <td className={tdClass}>
                <span className="tabular">{r.findings.length}</span>
                {r.findings.map((f) => (
                  <Link key={f.key} href={routes.finding(f.key)} className="quiet-link ml-2 font-mono text-xs">
                    {f.kind}
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

function Changes({
  result,
  since,
  rows,
  page,
}: {
  result: ApiResult<ChangesResponse>;
  since?: string;
  rows: number | "all";
  page: number;
}) {
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
  const slice = paginate(d.items, rows, page);
  const pageHref = (p: number) =>
    exploreHref({ since: d.since ?? since, crows: rows === ROWS_DEFAULT ? undefined : rows, cpage: p > 1 ? p : undefined }, "changes");
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
        <ReleaseSelect
          current={d.since ?? null}
          recentHref={exploreHref({ crows: rows === ROWS_DEFAULT ? undefined : rows }, "changes")}
          options={d.releases.map((r) => ({ release: r, href: exploreHref({ since: r, crows: rows === ROWS_DEFAULT ? undefined : rows }, "changes") }))}
        />
      ) : null}
      {d.items.length === 0 ? (
        <EmptyState title="No change in this window">
          No status, stage or milestone change was recorded {d.since ? `since ${d.since}` : "recently"}.
        </EmptyState>
      ) : (
        <TableWrap label="Recently changed KEPs">
          <table className={tableClass}>
            <caption className="mb-1 text-left text-xs text-fg-muted">
              <Pager slice={slice} href={pageHref} />
            </caption>
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
              {slice.shown.map((c, i) => (
                <tr key={`${c.kep_number}-${c.field}-${c.at_iso}-${i}`}>
                  <td className={cx(tdClass, "whitespace-nowrap font-mono text-xs")}>{isoUtc(c.at_iso) || <Dash />}</td>
                  <td className={cx(tdClass, "min-w-48")}>
                    <KepLink number={c.kep_number} /> <span className="text-sm">{c.kep_title}</span>
                    {c.owning_sig ? (
                      <span className="block text-xs">
                        {/* A 24 px high target (WCAG 2.5.8): it sits right under the KEP link. */}
                        <SigLink sig={c.owning_sig} className="inline-flex min-h-6 items-center" />
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
