import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense, type ReactNode } from "react";
import { serverApi } from "@/lib/api/server";
import { routes } from "@/lib/routes";
import type { ApiResult } from "@/lib/api/core";
import type { DecisionOut, GraphEdge, GraphNode, GraphOut, ItemList, KepCard, KepDetail, KepRef, StatusChangeOut, ToolSpec } from "@/lib/api/types";
import { FINDING_KIND_TEXT, humanize, isoDate, isoUtc, numberFromPath, pluralS, shortSha } from "@/lib/format";
import { fieldsOf } from "@/lib/schema";
import { EvidenceChain } from "@/components/EvidenceChain";
import { KeyLinks } from "@/components/KeyLinks";
import { Tabs } from "@/components/Tabs";
import { ToolResultView } from "@/components/ToolResultView";
import { PersonLink, SigLink } from "@/components/ui";
import { PagedTable } from "@/components/PagedTable";
import {
  Card,
  Chip,
  Dash,
  EmptyState,
  ErrorState,
  ExtLink,
  Facts,
  KepLink,
  SkeletonBlock,
  StatusChip,
  TableWrap,
  cx,
  tableClass,
  tdClass,
  thClass,
} from "@/components/ui";

export async function generateMetadata(props: PageProps<"/explore/kep/[number]">): Promise<Metadata> {
  const { number } = await props.params;
  const ok = /^\d+$/.test(number);
  return {
    title: ok ? `KEP-${number}` : "KEP",
    description: ok
      ? `KEP-${number}: facts, status history, who decided each state and on what evidence, lineage and open findings.`
      : undefined,
  };
}

export default function KepPage(props: PageProps<"/explore/kep/[number]">) {
  return (
    <Suspense fallback={<KepSkeleton />}>
      <KepBody params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}

function KepSkeleton() {
  return (
    <div className="space-y-6">
      <div className="skeleton h-8 w-2/3" />
      <div className="skeleton h-28 w-full" />
      <SkeletonBlock lines={8} label="Loading the KEP" />
    </div>
  );
}

async function KepBody({
  params,
  searchParams,
}: {
  params: PageProps<"/explore/kep/[number]">["params"];
  searchParams: PageProps<"/explore/kep/[number]">["searchParams"];
}) {
  const { number } = await params;
  const sp = await searchParams;
  const path = typeof sp.path === "string" ? sp.path : undefined;
  if (!/^\d+$/.test(number)) notFound();

  const [kep, history, decisions, tools] = await Promise.all([
    serverApi.kep(number, path),
    serverApi.kepHistory(number, path),
    serverApi.kepDecisions(number, path),
    serverApi.tools(),
  ]);

  if (!kep.ok) {
    if (kep.error.code === "not_found" || kep.error.status === 404) notFound();
    if (kep.error.code === "ambiguous_reference") {
      const candidates = (kep.error.details?.candidates ?? []) as KepCard[];
      return <Ambiguous number={number} candidates={candidates} />;
    }
    return (
      <>
        <h1 className="mb-4 text-xl font-semibold">
          <span className="font-mono">KEP-{number}</span>
        </h1>
        <ErrorState error={kep.error} what="KEP" />
      </>
    );
  }
  const k = kep.data;
  // Feature detection: the section exists only when the API registers impact_of_change and its schema accepts a KEP reference.
  const impactTool = tools.ok ? tools.data.items.find((t) => t.name === IMPACT_TOOL) : undefined;
  const impactParams = impactTool ? kepParamsFor(impactTool, k) : null;
  return (
    <div className="space-y-6">
      <Header k={k} />
      <Card title="Facts">
        <KepFacts k={k} />
      </Card>
      <Tabs
        label="KEP details"
        tabs={[
          { id: "decisions", label: "Decisions", content: <Decisions result={decisions} /> },
          { id: "history", label: "Status history", content: <History result={history} /> },
          { id: "people", label: "People", content: <People k={k} /> },
          { id: "lineage", label: "Lineage", content: <Lineage k={k} /> },
          { id: "findings", label: `Findings (${k.findings.length})`, content: <Findings k={k} /> },
          { id: "sections", label: "Sections", content: <Sections k={k} /> },
        ]}
      />
      {impactTool && impactParams ? (
        <Suspense
          fallback={
            <Card title="Impact of change" id="impact">
              <SkeletonBlock lines={4} label={`Running ${IMPACT_TOOL}`} />
            </Card>
          }
        >
          <Impact tool={impactTool} params={impactParams} />
        </Suspense>
      ) : null}
    </div>
  );
}

const IMPACT_TOOL = "impact_of_change";

/** Parameters that point a tool at this KEP, read from its schema: a `kep_ref`-style field, or the single required text field. */
function kepParamsFor(tool: ToolSpec, k: KepDetail): Record<string, unknown> | null {
  const fields = fieldsOf(tool.params_schema);
  const byName = fields.find((f) => ["kep_ref", "kep", "kep_key", "kep_path"].includes(f.name) && f.kind === "text");
  if (byName) return { [byName.name]: k.key };
  const byNumber = fields.find((f) => ["kep_number", "number"].includes(f.name) && f.kind === "integer");
  if (byNumber && k.number !== null) return { [byNumber.name]: k.number };
  const required = fields.filter((f) => f.required);
  if (required.length === 1 && required[0].kind === "text") return { [required[0].name]: k.key };
  return null;
}

async function Impact({ tool, params }: { tool: ToolSpec; params: Record<string, unknown> }) {
  const res = await serverApi.runTool(tool.name, params);
  return (
    <Card
      title="Impact of change"
      id="impact"
      actions={
        <Link href={`/tools?tool=${encodeURIComponent(tool.name)}` as Route} className="quiet-link text-sm">
          Run with other parameters
        </Link>
      }
    >
      <p className="mb-3 max-w-[80ch] text-sm text-fg-secondary">{tool.description}</p>
      {res.ok ? <ToolResultView name={tool.name} params={params} result={res.data} /> : <ErrorState error={res.error} what={tool.name} />}
    </Card>
  );
}

function Ambiguous({ number, candidates }: { number: string; candidates: KepCard[] }) {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">
        More than one KEP uses the number <span className="font-mono">{number}</span>
      </h1>
      <p className="text-fg-secondary">Pick the KEP you mean; each lives in a different directory.</p>
      <ul className="space-y-2">
        {candidates.map((c) => (
          <li key={c.key} className="rounded-md border border-border bg-surface p-3">
            <Link href={routes.kepPath(number, c.key)} className="quiet-link font-mono">
              {c.key}
            </Link>
            <p className="text-sm">{c.title}</p>
            <p className="text-xs text-fg-muted">
              <span className="font-mono">{c.owning_sig}</span> · {c.status}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Header({ k }: { k: KepDetail }) {
  const n = k.number ?? numberFromPath(k.key);
  const ask = `Trace the decisions on KEP-${n}: who decided each stage change, and is the metadata current?`;
  const askHref = `/ask?q=${encodeURIComponent(ask)}` as Route;
  return (
    <header className="border-b border-border pb-6">
      <KeyLinks
        links={[
          { key: "o", href: k.url },
          { key: "y", href: k.source_url },
          { key: "a", href: askHref },
        ]}
      />
      <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        {n !== null ? <span className="eyebrow !text-fg-secondary">KEP-{n}</span> : null}
        <span className="font-mono text-xs text-fg-muted">{k.key}</span>
      </p>
      <h1 className="display mt-2 max-w-[28ch] text-2xl font-semibold">{k.title}</h1>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusChip status={k.status} />
        {k.stage ? <Chip mono>{k.stage}</Chip> : null}
        {k.owning_sig ? (
          <Chip mono>
            <SigLink sig={k.owning_sig} className="quiet-link" />
          </Chip>
        ) : null}
        {k.latest_milestone ? <Chip mono>latest {k.latest_milestone}</Chip> : null}
        {k.open_findings > 0 ? (
          <Chip tone="warning">
            {k.open_findings} open finding{pluralS(k.open_findings)}
          </Chip>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-sm">
        <span className="inline-flex items-center gap-1.5">
          <ExtLink href={k.url}>KEP on GitHub</ExtLink> <kbd aria-hidden="true">o</kbd>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ExtLink href={k.source_url}>kep.yaml</ExtLink> <kbd aria-hidden="true">y</kbd>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Link href={askHref} className="quiet-link">
            Ask about this KEP
          </Link>{" "}
          <kbd aria-hidden="true">a</kbd>
        </span>
      </div>
      {k.summary ? (
        k.summary.length > 360 ? (
          <details className="mt-4 max-w-[70ch] text-md text-fg-secondary">
            <summary className="cursor-pointer">{k.summary.slice(0, 360).trimEnd()}… <span className="text-accent">Full summary</span></summary>
            <p className="mt-2">{k.summary}</p>
          </details>
        ) : (
          <p className="mt-4 max-w-[70ch] text-md text-fg-secondary">{k.summary}</p>
        )
      ) : null}
    </header>
  );
}

function people(list: { login: string; url: string }[]): ReactNode {
  if (list.length === 0) return <Dash />;
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {list.map((p) => (
        <PersonLink key={p.login} login={p.login} />
      ))}
    </span>
  );
}

function KepFacts({ k }: { k: KepDetail }) {
  const ms = k.milestones;
  const stages: [string, string | null][] = [
    ["alpha", ms.alpha],
    ["beta", ms.beta],
    ["stable", ms.stable],
    ["deprecated", ms.deprecated],
    ["disabled", ms.disabled],
    ["removed", ms.removed],
  ];
  const set = stages.filter(([, v]) => v);
  const ti = k.tracking_issue;
  return (
    <Facts
      items={[
        { label: "Authors", value: people(k.authors) },
        { label: "Approvers", value: people(k.approvers) },
        { label: "Reviewers", value: people(k.reviewers) },
        {
          label: "PRR approvers",
          value:
            k.prr_approvers.length === 0 ? (
              <Dash />
            ) : (
              <span className="flex flex-wrap gap-x-3 gap-y-1">
                {k.prr_approvers.map((p) => (
                  <span key={`${p.login}-${p.stage}`}>
                    <PersonLink login={p.login} />
                    {p.stage ? <span className="ml-1 font-mono text-xs text-fg-muted">{p.stage}</span> : null}
                  </span>
                ))}
              </span>
            ),
        },
        {
          label: "Tracking issue",
          value: ti ? (
            <span>
              <ExtLink href={ti.url}>
                <span className="font-mono">#{ti.number}</span>
              </ExtLink>{" "}
              <Chip tone={ti.state === "closed" ? "neutral" : "accent"}>{ti.state}</Chip>
              {ti.state_reason ? <span className="ml-1 font-mono text-xs text-fg-muted">{ti.state_reason}</span> : null}
              {ti.closed_at_iso ? <span className="block font-mono text-xs text-fg-muted">closed {isoUtc(ti.closed_at_iso)}</span> : null}
              {ti.milestone ? <span className="block text-xs">milestone <span className="font-mono">{ti.milestone}</span></span> : null}
              {ti.labels.length ? (
                <span className="mt-1 flex flex-wrap gap-1">
                  {ti.labels.map((l) => (
                    <span key={l} className="rounded-sm border border-border bg-surface-subtle px-1 font-mono text-xs">
                      {l}
                    </span>
                  ))}
                </span>
              ) : null}
            </span>
          ) : (
            <span className="text-fg-secondary">No tracking issue recorded</span>
          ),
        },
        {
          label: "Milestones",
          value: set.length ? (
            <span className="flex flex-wrap gap-x-3">
              {set.map(([s, v]) => (
                <span key={s}>
                  {s} <span className="font-mono">{v}</span>
                </span>
              ))}
            </span>
          ) : (
            <Dash />
          ),
        },
        {
          label: "Participating SIGs",
          value: k.participating_sigs.length ? (
            <span className="flex flex-wrap gap-x-3">
              {k.participating_sigs.map((sig) => (
                <SigLink key={sig} sig={sig} />
              ))}
            </span>
          ) : (
            <Dash />
          ),
        },
        {
          label: "Feature gates",
          value: k.feature_gates.length ? <span className="font-mono break-all">{k.feature_gates.join(", ")}</span> : <Dash />,
        },
        {
          label: "Created / last updated",
          value: (
            <span className="font-mono">
              {k.creation_date ?? <Dash />} / {k.last_updated ?? <Dash />}
            </span>
          ),
        },
      ]}
    />
  );
}

function Decisions({ result }: { result: ApiResult<ItemList<DecisionOut>> }) {
  if (!result.ok) return <ErrorState error={result.error} what="Decisions" />;
  const items = result.data.items;
  if (items.length === 0)
    return (
      <EmptyState title="No decisions derived for this KEP">
        Decisions are derived from merged status changes in kep.yaml and the tracking issue&apos;s label and milestone events.
      </EmptyState>
    );
  return (
    <TableWrap label="Decisions">
      <table className={tableClass}>
        <caption className="mb-1 text-left text-xs text-fg-muted">Who decided each state, with the evidence.</caption>
        <thead>
          <tr>
            <th className={thClass}>Decided</th>
            <th className={thClass}>Decision</th>
            <th className={thClass}>Deciders</th>
            <th className={thClass}>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.key}>
              <td className={cx(tdClass, "font-mono whitespace-nowrap text-xs")}>{isoUtc(d.decided_at_iso)}</td>
              <td className={cx(tdClass, "min-w-48")}>
                <span className="font-mono text-xs text-fg-muted">{d.kind}</span>
                <p>{d.summary}</p>
                {!d.human_decider ? <p className="text-xs text-fg-secondary">Merged by automation after human approval.</p> : null}
              </td>
              <td className={cx(tdClass, "min-w-40")}>
                {d.deciders.length === 0 ? (
                  <Dash />
                ) : (
                  <ul className="space-y-1">
                    {d.deciders.map((p) => (
                      <li key={`${p.login}-${p.role}`}>
                        <PersonLink login={p.login} /> <span className="font-mono text-xs text-fg-muted">{p.role}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </td>
              <td className={cx(tdClass, "min-w-40")}>
                {d.evidence.length === 0 ? (
                  <Dash />
                ) : (
                  <ul className="space-y-1">
                    {d.evidence.map((e) => (
                      <li key={e.evidence_id}>
                        <span className="text-xs text-fg-muted">{e.label}</span> <ExtLink href={e.url}>{e.title ?? e.key}</ExtLink>
                      </li>
                    ))}
                  </ul>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

function History({ result }: { result: ApiResult<ItemList<StatusChangeOut>> }) {
  if (!result.ok) return <ErrorState error={result.error} what="Status history" />;
  const items = result.data.items;
  if (items.length === 0)
    return <EmptyState title="No status history recorded">No metadata, label or milestone change has been ingested for this KEP.</EmptyState>;
  return (
    <PagedTable
      label="Status history"
      caption="Metadata, label and milestone changes, oldest first."
      head={
        <tr>
          <th className={thClass}>At</th>
          <th className={thClass}>Kind</th>
          <th className={thClass}>Field</th>
          <th className={thClass}>Change</th>
          <th className={thClass}>Actor</th>
          <th className={thClass}>Evidence</th>
        </tr>
      }
      rows={items.map((c) => (
        <tr key={c.key}>
          <td className={cx(tdClass, "font-mono whitespace-nowrap text-xs")}>{isoUtc(c.at_iso)}</td>
          <td className={cx(tdClass, "font-mono text-xs")}>{c.kind}</td>
          <td className={cx(tdClass, "font-mono")}>
            {c.field}
            {c.op ? <span className="text-fg-muted"> {c.op}</span> : null}
          </td>
          <td className={cx(tdClass, "font-mono")}>
            {c.from_value ?? <Dash />} → {c.to_value ?? <Dash />}
            {c.is_reversal ? (
              <span className="ml-2">
                <Chip tone="warning">reversal</Chip>
              </span>
            ) : null}
          </td>
          <td className={tdClass}>{c.actor_login ? <PersonLink login={c.actor_login} /> : <Dash />}</td>
          <td className={tdClass}>
            <span className="flex flex-wrap gap-x-3">
              {c.commit_sha ? (
                <ExtLink href={c.source_url}>
                  <span className="font-mono">{shortSha(c.commit_sha)}</span>
                </ExtLink>
              ) : c.source_url ? (
                <ExtLink href={c.source_url}>source</ExtLink>
              ) : null}
              {c.pr ? (
                <ExtLink href={c.pr.url}>
                  <span className="font-mono">PR #{c.pr.number}</span>
                </ExtLink>
              ) : null}
              {!c.source_url && !c.pr ? <Dash /> : null}
            </span>
          </td>
        </tr>
      ))}
    />
  );
}

function People({ k }: { k: KepDetail }) {
  const rows: { login: string; url: string; rel: string }[] = [
    ...k.authors.map((p) => ({ ...p, rel: "AUTHORED" })),
    ...k.reviewers.map((p) => ({ ...p, rel: "REVIEWS" })),
    ...k.approvers.map((p) => ({ ...p, rel: "APPROVES" })),
    ...k.prr_approvers.map((p) => ({ login: p.login, url: p.url, rel: `PRR_APPROVED${p.stage ? ` {stage: ${p.stage}}` : ""}` })),
  ];
  if (rows.length === 0) return <EmptyState title="No people recorded">kep.yaml lists no authors, reviewers or approvers.</EmptyState>;
  return (
    <TableWrap label="People and roles">
      <table className={tableClass}>
        <caption className="mb-1 text-left text-xs text-fg-muted">
          Relationships as stored, Person → KEP, from{" "}
          <ExtLink href={k.source_url}>kep.yaml</ExtLink>
        </caption>
        <thead>
          <tr>
            <th className={thClass}>Person</th>
            <th className={thClass}>Relationship</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={`${r.login}-${r.rel}-${i}`}>
              <td className={tdClass}>
                <PersonLink login={r.login} /> <ExtLink href={r.url} label={`@${r.login} on GitHub`}><span className="sr-only">GitHub</span></ExtLink>
              </td>
              <td className={cx(tdClass, "font-mono")}>—{r.rel}→</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

function lineageGraph(k: KepDetail): GraphOut {
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];
  const add = (r: { key: string; title: string | null; url: string }) => {
    if (!nodes.has(r.key)) nodes.set(r.key, { id: r.key, key: r.key, label: "KEP", title: r.title, url: r.url });
  };
  add({ key: k.key, title: k.title, url: k.url });
  const rel = (list: KepRef[], type: string, outgoing: boolean) => {
    for (const r of list) {
      add(r);
      edges.push(outgoing ? { source: k.key, target: r.key, type } : { source: r.key, target: k.key, type });
    }
  };
  rel(k.relations.replaces, "REPLACES", true);
  rel(k.relations.replaced_by, "REPLACES", false);
  rel(k.relations.see_also, "SEE_ALSO", true);
  return { nodes: Array.from(nodes.values()), edges };
}

function Lineage({ k }: { k: KepDetail }) {
  const g = lineageGraph(k);
  const rows: { dir: string; r: KepRef }[] = [
    ...k.relations.replaces.map((r) => ({ dir: "replaces", r })),
    ...k.relations.replaced_by.map((r) => ({ dir: "replaced by", r })),
    ...k.relations.see_also.map((r) => ({ dir: "see also", r })),
  ];
  if (rows.length === 0)
    return <EmptyState title="No lineage recorded">This KEP declares no replaces, superseded-by or see-also relation, and no KEP declares one towards it.</EmptyState>;
  return (
    <div className="space-y-4">
      <EvidenceChain
        graph={g}
        rootIds={[k.key]}
        label={`Lineage of ${k.key}: ${g.nodes.length} KEPs and ${g.edges.length} relations`}
        emptyText="No lineage."
      />
      <TableWrap label="Lineage">
        <table className={tableClass}>
          <caption className="mb-1 text-left text-xs text-fg-muted">Relations and who declared them</caption>
          <thead>
            <tr>
              <th className={thClass}>Relation</th>
              <th className={thClass}>KEP</th>
              <th className={thClass}>Status</th>
              <th className={thClass}>Declared by</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ dir, r }) => {
              const n = r.number ?? numberFromPath(r.key);
              return (
                <tr key={`${dir}-${r.key}`}>
                  <td className={tdClass}>{dir}</td>
                  <td className={tdClass}>
                    <KepLink number={n} label={n !== null ? `KEP-${n}` : r.key} /> <span className="text-sm">{r.title}</span>
                  </td>
                  <td className={tdClass}>{r.status ? <StatusChip status={r.status} /> : <Dash />}</td>
                  <td className={cx(tdClass, "font-mono text-xs")}>{r.declared_by ?? <Dash />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableWrap>
    </div>
  );
}

function Findings({ k }: { k: KepDetail }) {
  if (k.findings.length === 0)
    return <EmptyState title="No findings">The detector found no disagreement between this KEP&apos;s records.</EmptyState>;
  return (
    <ul className="space-y-3">
      {k.findings.map((f) => (
        <li key={f.key} className="rounded-md border border-border bg-surface p-3">
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-medium">{f.kind}</span>
            <Chip tone={f.state === "open" ? "warning" : "neutral"}>{f.state}</Chip>
          </p>
          {FINDING_KIND_TEXT[f.kind] ? <p className="text-sm text-fg-secondary">{FINDING_KIND_TEXT[f.kind]}</p> : null}
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-xs text-fg-muted">{f.a_label}</p>
              <p className="font-mono text-sm">{f.a_value ?? <Dash />}</p>
              <ExtLink href={f.a_url} className="text-xs">
                source
              </ExtLink>
            </div>
            <div>
              <p className="text-xs text-fg-muted">{f.b_label}</p>
              <p className="font-mono text-sm">{f.b_value ?? <Dash />}</p>
              <ExtLink href={f.b_url} className="text-xs">
                source
              </ExtLink>
            </div>
          </div>
          {f.suggested_fix ? (
            <p className="mt-2 text-sm">
              Suggested fix: <span className="font-mono">{humanize(f.suggested_fix)}</span>
            </p>
          ) : null}
          <p className="mt-1 text-xs text-fg-muted">
            Detected <span className="font-mono">{isoDate(f.detected_at_iso)}</span> ·{" "}
            <Link href={routes.finding(f.key, "row")} className="quiet-link">
              Open in Audit
            </Link>
          </p>
        </li>
      ))}
    </ul>
  );
}

function Sections({ k }: { k: KepDetail }) {
  if (k.sections.length === 0) return <EmptyState title="No README sections loaded" />;
  return (
    <ul className="columns-1 gap-6 md:columns-2">
      {k.sections.map((s) => (
        <li key={s.anchor} className="mb-1 break-inside-avoid">
          <ExtLink href={s.url}>{s.heading}</ExtLink>
          {s.kind ? <span className="ml-1 font-mono text-xs text-fg-muted">{s.kind}</span> : null}
        </li>
      ))}
    </ul>
  );
}
