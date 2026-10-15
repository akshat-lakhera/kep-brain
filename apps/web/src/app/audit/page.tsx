import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import { auditApi } from "@/lib/api/audit";
import type { ChangesResponse, FindingsResponse, SyncStatus } from "@/lib/api/types";
import type { ApiResult } from "@/lib/api/core";
import { FINDING_KIND_TEXT, isoUtc, ms, shortSha } from "@/lib/format";
import { kindLabel, kindTones, toneColor } from "@/lib/kinds";
import { releaseNames } from "@/lib/releases";
import { FindingsTable } from "@/components/FindingsTable";
import {
  Card,
  Chip,
  Dash,
  EmptyState,
  ErrorState,
  ExtLink,
  KepLink,
  MiniBar,
  PageHeader,
  PersonLink,
  SigLink,
  SkeletonBlock,
  StatTile,
  TableWrap,
  cx,
  tableClass,
  tdClass,
  thClass,
} from "@/components/ui";

export const metadata: Metadata = { title: "Audit" };

type Search = { kind?: string; sig?: string; state?: string; finding?: string; since?: string };

function one(v: string | string[] | undefined): string | undefined {
  return Array.isArray(v) ? v[0] : v || undefined;
}

const selectClass = "h-8 rounded-sm border border-border-input bg-surface px-2 text-base";

export default function AuditPage(props: PageProps<"/audit">) {
  return (
    <>
      <PageHeader
        title="Audit"
        lead="Decision records that disagree, and what to fix. Each finding is a KEP whose kep.yaml, tracking issue or replacement declaration say different things; both records link to GitHub, the people who set each value are named, and the fix is drafted from the evidence."
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
      <div className="skeleton h-12 w-full" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="skeleton h-24" />
        <div className="skeleton h-24" />
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
    since: one(sp.since),
  };
  const filtering = Boolean(filter.kind || filter.sig || filter.state);
  // The unfiltered summary feeds the filter options and colours; the filtered call feeds the tiles and the table.
  const [all, filtered, changes, sync] = await Promise.all([
    serverApi.findings({}),
    filtering ? serverApi.findings({ kind: filter.kind, sig: filter.sig, state: filter.state }) : Promise.resolve(null),
    auditApi.changes({ since: filter.since, sig: filter.sig }),
    auditApi.syncStatus(),
  ]);
  if (!all.ok) return <ErrorState error={all.error} what="Findings" />;
  const view: FindingsResponse | null = filtered === null ? all.data : filtered.ok ? filtered.data : null;
  const tones = kindTones(Object.keys(all.data.summary.by_kind));

  return (
    <div className="space-y-8">
      <Filters data={all.data} filter={filter} />
      <section id="findings" aria-labelledby="findings-h" className="space-y-4 scroll-mt-4">
        <h2 id="findings-h" className="sr-only">
          Findings
        </h2>
        {filtered && !filtered.ok ? (
          <ErrorState error={filtered.error} what="Filtered findings" />
        ) : view ? (
          <>
            <Summary data={view} tones={tones} filtering={filtering} />
            <FindingsTable
              items={view.items}
              selected={filter.finding}
              filtered={filtering}
              tones={Object.fromEntries(tones)}
            />
          </>
        ) : null}
      </section>
      <Changes result={changes} filter={filter} />
      <Sync result={sync} />
    </div>
  );
}

function Filters({ data, filter }: { data: FindingsResponse; filter: Search }) {
  const kinds = Object.keys(data.summary.by_kind).sort();
  const sigs = Object.keys(data.summary.by_sig).sort();
  const states = Array.from(new Set(data.items.map((f) => f.state))).sort();
  return (
    <form
      method="get"
      action="/audit"
      className="flex flex-wrap items-end gap-3 rounded-md border border-border bg-surface px-4 py-3"
      aria-label="Filter findings and changes"
    >
      <label className="flex flex-col gap-1 text-xs text-fg-secondary">
        Kind
        <select name="kind" defaultValue={filter.kind ?? ""} className={selectClass}>
          <option value="">All kinds</option>
          {kinds.map((k) => (
            <option key={k} value={k}>
              {kindLabel(k)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-fg-secondary">
        SIG
        <select name="sig" defaultValue={filter.sig ?? ""} className={selectClass}>
          <option value="">All SIGs</option>
          {sigs.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-fg-secondary">
        State
        <select name="state" defaultValue={filter.state ?? ""} className={selectClass}>
          <option value="">All states</option>
          {states.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </label>
      {filter.since ? <input type="hidden" name="since" value={filter.since} /> : null}
      <button type="submit" className="h-8 rounded-sm bg-accent px-3 font-medium text-on-accent hover:bg-accent-hover">
        Apply
      </button>
      {filter.kind || filter.sig || filter.state ? (
        <a href="/audit" className="quiet-link h-8 leading-8">
          Clear filters
        </a>
      ) : null}
      <nav aria-label="Sections" className="ml-auto flex gap-4 self-center text-sm">
        <a href="#findings" className="quiet-link">
          Findings
        </a>
        <a href="#changes" className="quiet-link">
          Changes
        </a>
        <a href="#sync" className="quiet-link">
          Sync
        </a>
      </nav>
    </form>
  );
}

function pct(v: number): string {
  return `${(v * 100).toFixed(1).replace(/\.0$/, "")}%`;
}

function Summary({ data, tones, filtering }: { data: FindingsResponse; tones: Map<string, number | null>; filtering: boolean }) {
  const s = data.summary;
  const kinds = Object.entries(s.by_kind).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const sigs = Object.entries(s.by_sig).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const maxKind = Math.max(0, ...kinds.map(([, v]) => v));
  const maxSig = Math.max(0, ...sigs.map(([, v]) => v));
  const checked = typeof s.hand_checked === "number" ? s.hand_checked : null;
  const precision = typeof s.precision === "number" ? s.precision : null;
  const scope = filtering ? " in this filter" : "";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label={`Findings${scope}`} value={s.total.toLocaleString("en-US")} note="pairs of records that disagree" />
        <StatTile label={`KEPs flagged${scope}`} value={s.flagged_keps.toLocaleString("en-US")} note="KEPs with at least one finding" />
        <StatTile
          label="Hand-checked"
          value={checked !== null ? checked.toLocaleString("en-US") : <Dash />}
          note={checked !== null ? `${checked.toLocaleString("en-US")} of ${s.total.toLocaleString("en-US")} findings` : "Not hand-checked yet"}
        />
        <StatTile
          label="Precision"
          value={precision !== null && checked ? pct(precision) : <Dash />}
          note={precision !== null && checked ? `correct of n = ${checked.toLocaleString("en-US")} hand-checked` : `0 of ${s.total.toLocaleString("en-US")} hand-checked`}
        />
      </div>
      <p className="text-sm text-fg-secondary">Recall is not measured: there is no complete list of disagreements to compare against.</p>
      <div className="grid gap-px overflow-hidden rounded-md border border-border bg-border md:grid-cols-2">
        <div className="bg-surface p-4">
          <h3 className="mb-2 text-xs font-medium text-fg-secondary">By kind</h3>
          {kinds.length === 0 ? (
            <p className="text-sm text-fg-secondary">No findings.</p>
          ) : (
            <ul className="space-y-2">
              {kinds.map(([k, v]) => (
                <li key={k} className="grid grid-cols-[minmax(0,14rem)_minmax(0,1fr)_3rem] items-center gap-3 text-sm">
                  <span className="min-w-0">
                    <a href={`/audit?kind=${encodeURIComponent(k)}#findings`} className="quiet-link block truncate" title={FINDING_KIND_TEXT[k] ?? k}>
                      {kindLabel(k)}
                    </a>
                    <span className="ident block truncate text-xs text-fg-muted">{k}</span>
                  </span>
                  <MiniBar value={v} max={maxKind} color={toneColor(tones.get(k))} />
                  <span className="tabular text-right">{v.toLocaleString("en-US")}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="bg-surface p-4">
          <h3 className="mb-2 text-xs font-medium text-fg-secondary">By owning SIG</h3>
          {sigs.length === 0 ? (
            <p className="text-sm text-fg-secondary">No findings.</p>
          ) : (
            <ul className="space-y-2">
              {sigs.map(([k, v]) => (
                <li key={k} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_3rem] items-center gap-3 text-sm">
                  <span className="truncate">
                    <SigLink sig={k} />
                  </span>
                  <MiniBar value={v} max={maxSig} />
                  <a
                    href={`/audit?sig=${encodeURIComponent(k)}#findings`}
                    className="quiet-link tabular text-right"
                    aria-label={`Show the ${v} findings in ${k}`}
                  >
                    {v.toLocaleString("en-US")}
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function SectionHead({ id, title, lead, children }: { id: string; title: string; lead: string; children?: React.ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 id={`${id}-h`} className="text-md font-semibold">
          {title}
        </h2>
        <p className="max-w-[80ch] text-sm text-fg-secondary">{lead}</p>
      </div>
      {children}
    </div>
  );
}

const CHANGE_TILES: { key: keyof ChangesResponse["counts"]; label: string }[] = [
  { key: "keps_changed", label: "KEPs changed" },
  { key: "status_transitions", label: "Status transitions" },
  { key: "stage_changes", label: "Stage changes" },
  { key: "new_keps", label: "New KEPs" },
];

function Changes({ result, filter }: { result: ApiResult<ChangesResponse>; filter: Search }) {
  const lead = "What moved in the decision records after a release: status, stage and milestone changes, who made them and in which PR.";
  if (!result.ok) {
    return (
      <section id="changes" aria-labelledby="changes-h" className="scroll-mt-4">
        <SectionHead id="changes" title="Changes since a release" lead={lead} />
        {result.error.status === 404 ? (
          <EmptyState title="Change tracking is not served by this API yet">
            <span className="ident">GET /v1/changes</span> answered 404. The table of status, stage and milestone changes appears here
            once the API exposes it.
          </EmptyState>
        ) : (
          <ErrorState error={result.error} what="Changes" />
        )}
      </section>
    );
  }
  const d = result.data;
  const releases = releaseNames(d.releases);
  const since = d.since ?? filter.since ?? null;
  const items = [...d.items].sort((a, b) => (b.at_iso ?? "").localeCompare(a.at_iso ?? ""));
  const scope = since ? `since ${since}` : "";
  return (
    <section id="changes" aria-labelledby="changes-h" className="scroll-mt-4">
      <SectionHead id="changes" title={since ? `Changes since ${since}` : "Changes since a release"} lead={lead}>
        {releases.length ? (
          <form method="get" action="/audit#changes" className="flex items-end gap-2" aria-label="Choose a release">
            {filter.kind ? <input type="hidden" name="kind" value={filter.kind} /> : null}
            {filter.sig ? <input type="hidden" name="sig" value={filter.sig} /> : null}
            {filter.state ? <input type="hidden" name="state" value={filter.state} /> : null}
            <label className="flex flex-col gap-1 text-xs text-fg-secondary">
              Since release
              <select name="since" defaultValue={since ?? ""} className={selectClass}>
                {releases.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className="h-8 rounded-sm border border-border-input bg-surface px-3">
              Show
            </button>
          </form>
        ) : null}
      </SectionHead>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {CHANGE_TILES.map((t) => (
          <StatTile
            key={t.key}
            label={t.label}
            value={(d.counts[t.key] ?? 0).toLocaleString("en-US")}
            note={
              t.key === "stage_changes"
                ? `${scope ? `${scope} · ` : ""}plus ${(d.counts.milestone_changes ?? 0).toLocaleString("en-US")} milestone changes`
                : scope || undefined
            }
          />
        ))}
      </div>
      <div className="mt-4 rounded-md border border-border bg-surface">
        {items.length === 0 ? (
          <p className="p-4 text-sm text-fg-secondary">
            No status, stage or milestone change {since ? `after ${since}` : "in this range"}
            {filter.sig ? (
              <>
                {" "}
                in <span className="ident">{filter.sig}</span>
              </>
            ) : null}
            .
          </p>
        ) : (
          <TableWrap label="Changes table">
            <table className={tableClass}>
              <caption className="sr-only">Changes {scope}, newest first</caption>
              <thead>
                <tr>
                  <th className={thClass}>KEP</th>
                  <th className={thClass}>Field</th>
                  <th className={thClass}>From → to</th>
                  <th className={thClass}>At</th>
                  <th className={thClass}>Actor</th>
                  <th className={thClass}>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c, i) => (
                  <tr key={`${c.kep_number}-${c.field}-${c.at_iso}-${i}`}>
                    <td className={cx(tdClass, "min-w-48")}>
                      <KepLink number={c.kep_number} />
                      {c.kep_title ? <p className="text-xs">{c.kep_title}</p> : null}
                      {c.owning_sig ? <SigLink sig={c.owning_sig} className="text-xs" /> : null}
                    </td>
                    <td className={tdClass}>
                      <span className="ident">{c.field}</span>
                      <p className="text-xs text-fg-muted">{c.kind}</p>
                    </td>
                    <td className={cx(tdClass, "ident whitespace-nowrap")}>
                      {c.from_value ?? <Dash />} → {c.to_value ?? <Dash />}
                    </td>
                    <td className={cx(tdClass, "ident tabular whitespace-nowrap text-fg-secondary")}>{isoUtc(c.at_iso) || <Dash />}</td>
                    <td className={tdClass}>{c.actor_login ? <PersonLink login={c.actor_login} /> : <Dash />}</td>
                    <td className={cx(tdClass, "whitespace-nowrap")}>
                      {c.pr ? (
                        <ExtLink href={c.pr.url}>
                          <span className="ident">#{c.pr.number}</span>
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
    </section>
  );
}

function Sync({ result }: { result: ApiResult<SyncStatus> }) {
  const lead = "Which upstream commits and issue snapshot the graph holds, and when the worker last refreshed it.";
  return (
    <section id="sync" aria-labelledby="sync-h" className="scroll-mt-4">
      <SectionHead id="sync" title="Sync status" lead={lead} />
      {!result.ok ? (
        result.error.status === 404 ? (
          <EmptyState title="Sync status is not served by this API yet">
            <span className="ident">GET /v1/sync/status</span> answered 404. The pinned commits and the issue snapshot time are in the
            header chip, from <span className="ident">GET /v1/meta</span>.
          </EmptyState>
        ) : (
          <ErrorState error={result.error} what="Sync status" />
        )
      ) : (
        <SyncCard s={result.data} />
      )}
    </section>
  );
}

function SyncCard({ s }: { s: SyncStatus }) {
  const run = s.last_run;
  const steps = run ? Object.entries(run.steps) : [];
  const labels = Object.entries(s.counts_by_label).sort((a, b) => b[1] - a[1]);
  return (
    <Card>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs text-fg-secondary">kubernetes/enhancements</dt>
          <dd>
            {s.pinned.enhancements_sha ? (
              <ExtLink href={`https://github.com/kubernetes/enhancements/tree/${s.pinned.enhancements_sha}`}>
                <span className="ident">{shortSha(s.pinned.enhancements_sha)}</span>
              </ExtLink>
            ) : (
              <Dash />
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-fg-secondary">kubernetes/community</dt>
          <dd>
            {s.pinned.community_sha ? (
              <ExtLink href={`https://github.com/kubernetes/community/tree/${s.pinned.community_sha}`}>
                <span className="ident">{shortSha(s.pinned.community_sha)}</span>
              </ExtLink>
            ) : (
              <Dash />
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-fg-secondary">Issues as of</dt>
          <dd className="ident tabular">{isoUtc(s.tickets_as_of) || <Dash />}</dd>
        </div>
        <div>
          <dt className="text-xs text-fg-secondary">Worker last seen · next tick</dt>
          <dd className="ident tabular">
            {isoUtc(s.worker_last_seen_iso) || "never"} · {isoUtc(s.next_tick_iso) || "none scheduled"}
          </dd>
        </div>
      </dl>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <p className="mb-1 flex flex-wrap items-center gap-2 text-xs font-medium text-fg-secondary">
            Last run
            {run ? <Chip tone={run.ok ? "success" : "danger"}>{run.ok ? "succeeded" : "failed"}</Chip> : null}
          </p>
          {!run ? (
            <p className="text-sm text-warning">No sync run is recorded yet.</p>
          ) : (
            <>
              <p className="ident text-xs text-fg-muted">
                {isoUtc(run.started_at_iso)} → {isoUtc(run.finished_at_iso) || "running"}
              </p>
              {steps.length ? (
                <table className={cx(tableClass, "mt-2")}>
                  <caption className="sr-only">Steps of the last sync run</caption>
                  <thead>
                    <tr>
                      <th className={thClass}>Step</th>
                      <th className={cx(thClass, "text-right")}>Items</th>
                      <th className={cx(thClass, "text-right")}>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {steps.map(([name, st]) => (
                      <tr key={name}>
                        <td className={cx(tdClass, "ident")}>{name}</td>
                        <td className={cx(tdClass, "tabular text-right")}>{typeof st.count === "number" ? st.count.toLocaleString("en-US") : <Dash />}</td>
                        <td className={cx(tdClass, "tabular text-right")}>{typeof st.ms === "number" ? ms(st.ms) : <Dash />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
            </>
          )}
        </div>
        <div>
          <p className="mb-1 text-xs font-medium text-fg-secondary">Nodes by label</p>
          {labels.length === 0 ? (
            <p className="text-sm text-fg-secondary">No counts reported.</p>
          ) : (
            <table className={tableClass}>
              <caption className="sr-only">Nodes in the graph by label</caption>
              <tbody>
                {labels.map(([l, n]) => (
                  <tr key={l}>
                    <td className={cx(tdClass, "ident py-1")}>{l}</td>
                    <td className={cx(tdClass, "tabular py-1 text-right")}>{n.toLocaleString("en-US")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <p className="mt-3 text-xs text-fg-muted">
        Answers and findings are computed against these pinned commits, so a sync that finds nothing new changes nothing on this
        page. <Link href={"/about" as Route} className="quiet-link">Sources and licences</Link>
      </p>
    </Card>
  );
}
