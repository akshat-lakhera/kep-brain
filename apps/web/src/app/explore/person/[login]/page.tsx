import type { Metadata } from "next";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { apiInternalUrl } from "@/lib/api/server";
import { exploreApi, explorePaths, exploreTemplates, isNotFound, routeServed } from "@/lib/api/explore";
import type { PersonOut } from "@/lib/api/types-explore";
import type { KepCard } from "@/lib/api/types";
import { isoDate, isoUtc, pluralS } from "@/lib/format";
import { Card, Chip, Dash, EmptyState, ErrorState, ExtLink, KepLink, SigLink, TableWrap, cx, tableClass, tdClass, thClass } from "@/components/ui";
import { KepTable } from "@/components/explore/KepTable";
import { Tabs } from "@/components/Tabs";
import { PagedTable } from "@/components/PagedTable";

const LOGIN = /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})$/;

export async function generateMetadata(props: PageProps<"/explore/person/[login]">): Promise<Metadata> {
  const { login } = await props.params;
  return { title: `@${login}`, description: `@${login}: SIG roles, KEPs authored, reviewed and approved, and the decisions they took part in.` };
}

// Blocking route (no Suspense above the fetch): a missing login must answer with a real HTTP 404.
export const instant = false;

export default async function PersonPage(props: PageProps<"/explore/person/[login]">) {
  const { login } = await props.params;
  if (!LOGIN.test(login)) notFound();
  await connection();
  const api = exploreApi(apiInternalUrl());
  const res = await api.person(login);
  if (!res.ok) {
    const missing = isNotFound(res.error);
    const served = missing ? routeServed(await api.openapi(), exploreTemplates.person) : true;
    if (missing && served) notFound();
    return (
      <div className="space-y-4">
        <h1 className="display mt-1 text-2xl font-semibold">
          <span className="font-mono">@{login}</span>
        </h1>
        {missing ? (
          <EmptyState title="Person pages are not available yet">
            The API does not answer <span className="font-mono">GET {explorePaths.person(login)}</span>, so nothing is known about this login here.
            KEP pages still list authors, reviewers and approvers.
          </EmptyState>
        ) : (
          <ErrorState error={res.error} what="Person" />
        )}
      </div>
    );
  }
  const p = res.data;
  const prr = p.keps.prr_approved;
  const counts = {
    authored: p.keps.authored.length,
    reviews: p.keps.reviews.length,
    approves: p.keps.approves.length,
    prr: prr.length,
  };
  const total = counts.authored + counts.reviews + counts.approves + counts.prr;
  return (
    <div className="space-y-6">
      <header className="border-b border-border pb-6">
        <h1 className="display mt-1 text-2xl font-semibold">
          <span className="font-mono">@{p.login}</span>
        </h1>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {p.is_bot ? <Chip>bot account</Chip> : null}
          {p.roles.map((r) => (
            <Chip key={`${r.org}-${r.role}`} mono>
              {r.role} · {r.org}
            </Chip>
          ))}
          <Chip>
            {total.toLocaleString("en-US")} KEP role{pluralS(total)}
          </Chip>
          <Chip>
            {p.decisions.length.toLocaleString("en-US")} decision{pluralS(p.decisions.length)}
          </Chip>
          <Chip>
            {p.owners.length.toLocaleString("en-US")} OWNERS entr{p.owners.length === 1 ? "y" : "ies"}
          </Chip>
        </div>
        <div className="mt-3 flex flex-wrap gap-4 text-sm">
          <ExtLink href={p.url}>GitHub profile</ExtLink>
          <Link href={`/ask?q=${encodeURIComponent(`What does @${p.login} own and decide on, and in which SIGs?`)}` as Route} className="quiet-link">
            Ask about this person
          </Link>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card title="Roles" id="roles">
          <Roles p={p} />
        </Card>
        <Card title="Who knows this area" id="connected">
          <Connectivity p={p} />
        </Card>
      </div>

      <Card title="KEP involvement" id="keps">
        {total === 0 ? (
          <EmptyState title="No KEP role recorded">
            No kep.yaml or PRR file in the loaded SIGs lists <span className="font-mono">@{p.login}</span> as author, reviewer, approver or PRR approver.
          </EmptyState>
        ) : (
          <Tabs
            label="KEP involvement"
            tabs={[
              { id: "authored", label: `Authored (${counts.authored})`, content: <Involvement items={p.keps.authored} rel="AUTHORED" /> },
              { id: "reviews", label: `Reviews (${counts.reviews})`, content: <Involvement items={p.keps.reviews} rel="REVIEWS" /> },
              { id: "approves", label: `Approves (${counts.approves})`, content: <Involvement items={p.keps.approves} rel="APPROVES" /> },
              {
                id: "prr",
                label: `PRR approved (${counts.prr})`,
                content: (
                  <Involvement
                    items={prr.map((x) => x.kep)}
                    rel="PRR_APPROVED"
                    extra={{ label: "Stage", values: Object.fromEntries(prr.map((x) => [x.kep.key, x.stage ?? ""])) }}
                  />
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card title="Decisions" id="decisions">
        <Decisions p={p} />
      </Card>

      <Card title="OWNERS directories" id="owners">
        <Owners p={p} />
      </Card>
    </div>
  );
}

function Roles({ p }: { p: PersonOut }) {
  if (p.roles.length === 0)
    return (
      <EmptyState title="No leadership role recorded">
        sigs.yaml lists no chair, tech lead, emeritus lead or subproject lead entry for this login in the loaded SIGs.
      </EmptyState>
    );
  return (
    <TableWrap label="Roles">
      <table className={tableClass}>
        <caption className="mb-1 text-left text-xs text-fg-muted">Leadership roles from sigs.yaml, as recorded.</caption>
        <thead>
          <tr>
            <th className={thClass}>Group</th>
            <th className={thClass}>Kind</th>
            <th className={thClass}>Role</th>
            <th className={thClass}>Valid from</th>
            <th className={thClass}>Source</th>
          </tr>
        </thead>
        <tbody>
          {p.roles.map((r, i) => (
            <tr key={`${r.org}-${r.role}-${i}`}>
              <td className={tdClass}>{r.org_kind === "sig" || r.org.startsWith("sig-") ? <SigLink sig={r.org} /> : <span className="font-mono">{r.org}</span>}</td>
              <td className={cx(tdClass, "font-mono text-xs")}>{r.org_kind ?? <Dash />}</td>
              <td className={cx(tdClass, "font-mono")}>{r.role}</td>
              <td className={cx(tdClass, "font-mono text-xs whitespace-nowrap")}>{isoDate(r.valid_from_iso) || <Dash />}</td>
              <td className={tdClass}>{r.source_url ? <ExtLink href={r.source_url}>sigs.yaml</ExtLink> : <Dash />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

function Connectivity({ p }: { p: PersonOut }) {
  const c = p.connectivity;
  if (!c)
    return (
      <EmptyState title="No connectivity score">
        The API returned no score for this login; it is computed only for people with at least one shared KEP.
      </EmptyState>
    );
  return (
    <div className="space-y-2">
      <p>
        <span className="text-2xl font-semibold tabular">{c.rank.toLocaleString("en-US")}</span>
        <span className="text-fg-secondary"> of {c.of.toLocaleString("en-US")} people</span>
      </p>
      <p className="text-sm">
        Score <span className="font-mono">{c.score.toLocaleString("en-US", { maximumFractionDigits: 4 })}</span>
      </p>
      <p className="text-sm text-fg-secondary">
        A higher rank means this person works on KEPs with more of the other people in the loaded SIGs, so they are more likely to know
        who to ask. It is a measure of shared work, not of expertise.
      </p>
      <p className="text-xs text-fg-muted">
        Method <span className="font-mono break-all">{c.method}</span>
      </p>
    </div>
  );
}

function Involvement({ items, rel, extra }: { items: KepCard[]; rel: string; extra?: { label: string; values: Record<string, string> } }) {
  if (items.length === 0)
    return (
      <EmptyState title={`No ${rel} relation`}>
        No KEP in the loaded SIGs records <span className="font-mono">—{rel}→</span> from this person.
      </EmptyState>
    );
  return <KepTable items={items} label={rel} caption={`Person —${rel}→ KEP, from kep.yaml${rel === "PRR_APPROVED" ? " and the PRR file" : ""}.`} extra={extra} />;
}

function Decisions({ p }: { p: PersonOut }) {
  if (p.decisions.length === 0)
    return (
      <EmptyState title="No decision recorded">
        This login does not appear as approver, lgtm, merger, PRR approver, author or actor on any derived decision in the loaded SIGs.
      </EmptyState>
    );
  const sorted = [...p.decisions].sort((a, b) => (b.decided_at_iso ?? "").localeCompare(a.decided_at_iso ?? ""));
  return (
    <PagedTable
      label="Decisions"
      caption={`${sorted.length.toLocaleString("en-US")} decision${pluralS(sorted.length)} this person is on, newest first.`}
      head={
        <tr>
          <th className={thClass}>Decided</th>
          <th className={thClass}>Role</th>
          <th className={thClass}>KEP</th>
          <th className={thClass}>Kind</th>
          <th className={thClass}>Decision</th>
          <th className={thClass}>Evidence</th>
        </tr>
      }
      rows={sorted.map((d) => (
        <tr key={`${d.key}-${d.role}`}>
          <td className={cx(tdClass, "whitespace-nowrap font-mono text-xs")}>{isoUtc(d.decided_at_iso) || <Dash />}</td>
          <td className={cx(tdClass, "font-mono text-xs")}>{d.role}</td>
          <td className={cx(tdClass, "min-w-48")}>
            <KepLink number={d.kep_number} /> <span className="text-sm">{d.kep_title}</span>
          </td>
          <td className={cx(tdClass, "font-mono text-xs")}>{d.kind}</td>
          <td className={cx(tdClass, "min-w-56")}>{d.summary ?? <Dash />}</td>
          <td className={cx(tdClass, "whitespace-nowrap")}>{d.url ? <ExtLink href={d.url}>evidence</ExtLink> : <Dash />}</td>
        </tr>
      ))}
    />
  );
}

function Owners({ p }: { p: PersonOut }) {
  if (p.owners.length === 0)
    return (
      <EmptyState title="No OWNERS entry">
        No loaded OWNERS file in kubernetes/kubernetes lists this login directly or through an alias.
      </EmptyState>
    );
  const sorted = [...p.owners].sort((a, b) => a.directory.localeCompare(b.directory) || a.role.localeCompare(b.role));
  return (
    <PagedTable
      label="OWNERS directories"
      caption="Directories this person can approve or review, from OWNERS and OWNERS_ALIASES at the ingested kubernetes/kubernetes commit."
      head={
        <tr>
          <th className={thClass}>Directory</th>
          <th className={thClass}>Role</th>
          <th className={thClass}>Via alias</th>
          <th className={thClass}>Source</th>
        </tr>
      }
      rows={sorted.map((o, i) => (
        <tr key={`${o.directory}-${o.role}-${i}`}>
          <td className={cx(tdClass, "font-mono")}>{o.directory}</td>
          <td className={cx(tdClass, "font-mono text-xs")}>{o.role}</td>
          <td className={cx(tdClass, "font-mono text-xs")}>{o.via_alias ?? <Dash />}</td>
          <td className={tdClass}>{o.source_url ? <ExtLink href={o.source_url}>OWNERS</ExtLink> : <Dash />}</td>
        </tr>
      ))}
    />
  );
}
