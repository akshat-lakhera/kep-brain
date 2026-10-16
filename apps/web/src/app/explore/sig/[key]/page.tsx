import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { apiInternalUrl } from "@/lib/api/server";
import { exploreApi, explorePaths, exploreTemplates, isNotFound, routeServed } from "@/lib/api/explore";
import type { SigDetail } from "@/lib/api/types-explore";
import { FINDING_KIND_TEXT, isoDate } from "@/lib/format";
import { Card, Chip, Dash, EmptyState, ErrorState, ExtLink, KepLink, TableWrap, cx, tableClass, tdClass, thClass } from "@/components/ui";
import { KepTable } from "@/components/explore/KepTable";
import { StatusBars } from "@/components/explore/StatusBars";
import { PersonLink, PersonList } from "@/components/explore/links";
import { PagedTable } from "@/components/PagedTable";

const KEY = /^[a-z0-9][a-z0-9-]{0,80}$/;

export async function generateMetadata(props: PageProps<"/explore/sig/[key]">): Promise<Metadata> {
  const { key } = await props.params;
  return { title: key };
}

// Blocking route (no Suspense above the fetch): an unknown SIG must answer with a real HTTP 404.
export const instant = false;

export default async function SigPage(props: PageProps<"/explore/sig/[key]">) {
  const { key } = await props.params;
  if (!KEY.test(key)) notFound();
  await connection();
  const api = exploreApi(apiInternalUrl());
  const res = await api.sig(key);
  if (!res.ok) {
    const missing = isNotFound(res.error);
    const served = missing ? routeServed(await api.openapi(), exploreTemplates.sig) : true;
    if (missing && served) notFound();
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-semibold">
          <span className="font-mono">{key}</span>
        </h1>
        {missing ? (
          <EmptyState title="SIG pages are not available yet">
            The API does not answer <span className="font-mono">GET {explorePaths.sig(key)}</span>. The audit lists this SIG&apos;s open findings and
            the top-bar search finds its KEPs by title.{" "}
            <Link href={`/audit?sig=${encodeURIComponent(key)}` as Route} className="quiet-link">
              Open the audit for {key}
            </Link>
          </EmptyState>
        ) : (
          <ErrorState error={res.error} what="SIG" />
        )}
      </div>
    );
  }
  const s = res.data;
  const openFindings = s.findings.filter((f) => f.state === "open");
  return (
    <div className="space-y-6">
      <header>
        <p className="font-mono text-sm text-fg-muted">{s.key}</p>
        <h1 className="text-xl font-semibold">{s.display_name ?? s.key}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Chip>
            {s.keps.length.toLocaleString("en-US")} KEP{s.keps.length === 1 ? "" : "s"}
          </Chip>
          {s.open_findings > 0 ? (
            <Chip tone="warning">
              {s.open_findings.toLocaleString("en-US")} open finding{s.open_findings === 1 ? "" : "s"}
            </Chip>
          ) : (
            <Chip tone="success">no open findings</Chip>
          )}
          {!s.in_scope ? <Chip>KEPs not loaded for this SIG</Chip> : null}
        </div>
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          {s.url ? <ExtLink href={s.url}>SIG on GitHub</ExtLink> : null}
          <Link href={`/audit?sig=${encodeURIComponent(s.key)}` as Route} className="quiet-link">
            Findings in Audit
          </Link>
          <Link href={`/?q=${encodeURIComponent(`Which KEPs in ${s.key} have metadata that is not current, and who decided their latest state?`)}` as Route} className="quiet-link">
            Ask about this SIG
          </Link>
        </div>
        {s.mission ? <p className="mt-3 max-w-[80ch] text-fg-secondary">{s.mission}</p> : null}
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="Leads" id="leads">
          <dl className="space-y-3">
            <div>
              <dt className="text-sm text-fg-secondary">Chairs</dt>
              <dd className="mt-0.5">{s.chairs.length ? <PersonList people={s.chairs} /> : <Dash />}</dd>
            </div>
            <div>
              <dt className="text-sm text-fg-secondary">Tech leads</dt>
              <dd className="mt-0.5">{s.tech_leads.length ? <PersonList people={s.tech_leads} /> : <Dash />}</dd>
            </div>
          </dl>
        </Card>
        <Card title="Subprojects" id="subprojects">
          {s.subprojects.length === 0 ? (
            <EmptyState title="No subproject recorded">sigs.yaml lists no subproject for this SIG.</EmptyState>
          ) : (
            <ul className="columns-1 gap-4 sm:columns-2 lg:columns-1">
              {s.subprojects.map((sp) => (
                <li key={sp.name} className="mb-1 break-inside-avoid font-mono text-sm">
                  {sp.url ? <ExtLink href={sp.url}>{sp.name}</ExtLink> : sp.name}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="KEPs by status" id="by-status">
          {Object.keys(s.keps_by_status).length === 0 ? (
            <EmptyState title="No KEP loaded for this SIG">Only SIGs within the loaded set have their kep.yaml files read.</EmptyState>
          ) : (
            <StatusBars counts={s.keps_by_status} caption="kep.yaml status of each KEP this SIG owns." />
          )}
        </Card>
      </div>

      <Card title="Open findings" id="findings">
        <Findings s={s} open={openFindings} />
      </Card>

      <Card title="KEPs" id="keps">
        {s.keps.length === 0 ? (
          <EmptyState title="No KEP loaded for this SIG">No kep.yaml with this owning-sig was read.</EmptyState>
        ) : (
          <KepTable items={s.keps} label="KEPs" hideSig caption={`${s.keps.length.toLocaleString("en-US")} KEPs owned by ${s.key}; click a header to sort.`} />
        )}
      </Card>

      <Card title="People" id="people">
        <People s={s} />
      </Card>
    </div>
  );
}

function Findings({ s, open }: { s: SigDetail; open: SigDetail["findings"] }) {
  if (open.length === 0)
    return (
      <EmptyState title="Nothing unresolved">
        {s.findings.length
          ? `${s.findings.length.toLocaleString("en-US")} finding${s.findings.length === 1 ? "" : "s"} for this SIG, all closed or triaged.`
          : "The detector found no disagreement between kep.yaml, tracking issues and replacement declarations for this SIG's KEPs."}
      </EmptyState>
    );
  return (
    <TableWrap label="Open findings">
      <table className={tableClass}>
        <caption className="mb-1 text-left text-xs text-fg-muted">
          {open.length.toLocaleString("en-US")} place{open.length === 1 ? "" : "s"} where this SIG&apos;s records disagree; each links to both sides in the audit.
        </caption>
        <thead>
          <tr>
            <th className={thClass}>KEP</th>
            <th className={thClass}>Kind</th>
            <th className={thClass}>Disagreement</th>
            <th className={thClass}>Detected</th>
            <th className={thClass}>Audit</th>
          </tr>
        </thead>
        <tbody>
          {open.map((f) => (
            <tr key={f.key}>
              <td className={cx(tdClass, "min-w-48")}>
                <KepLink number={f.kep_number} /> <span className="text-sm">{f.kep_title}</span>
              </td>
              <td className={cx(tdClass, "font-mono text-xs")}>
                {f.kind}
                {FINDING_KIND_TEXT[f.kind] ? <span className="block max-w-[40ch] font-sans text-fg-secondary">{FINDING_KIND_TEXT[f.kind]}</span> : null}
              </td>
              <td className={cx(tdClass, "min-w-56 text-xs")}>
                <span className="text-fg-muted">{f.a_label}</span> <span className="font-mono">{f.a_value ?? "∅"}</span>
                <br />
                <span className="text-fg-muted">{f.b_label}</span> <span className="font-mono">{f.b_value ?? "∅"}</span>
              </td>
              <td className={cx(tdClass, "whitespace-nowrap font-mono text-xs")}>{isoDate(f.detected_at_iso) || <Dash />}</td>
              <td className={cx(tdClass, "whitespace-nowrap")}>
                <Link href={`/audit?finding=${encodeURIComponent(f.key)}#f-${encodeURIComponent(f.key)}` as Route} className="quiet-link">
                  both sides
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

function People({ s }: { s: SigDetail }) {
  if (s.people.length === 0)
    return <EmptyState title="No people recorded">No kep.yaml, PRR file or sigs.yaml entry in this SIG names a person.</EmptyState>;
  const sorted = [...s.people].sort((a, b) => b.roles.length - a.roles.length || a.login.localeCompare(b.login));
  return (
    <PagedTable
      label="People"
      caption={`${sorted.length.toLocaleString("en-US")} people with a role on this SIG or its KEPs, most roles first.`}
      head={
        <tr>
          <th className={thClass}>Person</th>
          <th className={thClass}>Roles</th>
        </tr>
      }
      rows={sorted.map((p) => (
        <tr key={p.login}>
          <td className={cx(tdClass, "whitespace-nowrap")}>
            <PersonLink login={p.login} />
          </td>
          <td className={tdClass}>
            <span className="flex flex-wrap gap-1">
              {p.roles.map((r) => (
                <span key={r} className="rounded-sm border border-border bg-surface-subtle px-1 font-mono text-xs">
                  {r}
                </span>
              ))}
            </span>
          </td>
        </tr>
      ))}
    />
  );
}
