import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import { FINDING_KIND_TEXT, humanize, isoUtc, shortSha } from "@/lib/format";
import { SHORTCUT_GROUPS } from "@/lib/shortcuts";
import { Keys } from "@/components/Shortcuts";
import { Card, ErrorState, ExtLink, Facts, PageHeader, SkeletonBlock, StatTile, TableWrap, cx, tableClass, tdClass, thClass } from "@/components/ui";

export const metadata: Metadata = {
  title: "About",
  description:
    "What a KEP is, what KEP Brain reads, how the graph is built, how answers are produced and checked, the five audit checks, scope, licences, privacy, terms, accessibility and keyboard shortcuts.",
  alternates: { canonical: "/about" },
};

const REPO = "https://github.com/akshat-lakhera/kep-brain";
const ENH = "https://github.com/kubernetes/enhancements";
const PROCESS_DOC = `${ENH}/blob/master/keps/sig-architecture/0000-kep-process/README.md`;

// The process document's own definitions, quoted.
const STATUSES: [string, string][] = [
  ["provisional", "The KEP has been proposed and is actively being defined."],
  ["implementable", "The approvers have approved this KEP for implementation."],
  ["implemented", "The KEP has been implemented and is no longer actively changed."],
  ["deferred", "The KEP is proposed but not actively being worked on."],
  ["rejected", "The approvers and authors have decided that this KEP is not moving forward."],
  ["withdrawn", "The authors have withdrawn the KEP."],
  ["replaced", "The KEP has been replaced by a new KEP. The superseded-by metadata value should point to the new KEP."],
];

const KINDS = [
  "active_status_closed_issue",
  "terminal_status_future_targets",
  "one_sided_replacement",
  "stage_mismatch",
  "milestone_mismatch",
];

const NODES: [string, string][] = [
  ["KEP", "one per proposal folder, with the kep.yaml fields as properties"],
  ["Document, Section", "the kep.yaml, README (split by heading), PRR file, sigs.yaml and the KEP process documents"],
  ["Person, Alias, SIG, Subproject, OwnersFile", "who is who, from sigs.yaml and OWNERS files; GitHub logins only"],
  ["Issue, PullRequest, Commit, Review, Comment", "the tracking issue, its timeline, and the pull requests that changed each file"],
  ["StatusChange", "one per field change in a kep.yaml revision or per issue label and milestone event"],
  ["Decision", "derived from status, stage and milestone changes, PRR approvals and replacement declarations, linked to deciders and evidence"],
  ["Finding", "one per disagreement between two records, with both sides, a suggested fix and a lifecycle"],
  ["Release, FeatureGate, Label", "the targets a KEP points at"],
];

// Copied from the path_to_decision tool (apps/api/src/app/tools/t01/decision_path.py, VIA_EVIDENCE).
const DECISION_EVIDENCE_QUERY = `MATCH (p:Person {key: $login})-[r:SUBMITTED|COMMENTED]->(x)<-[e:EVIDENCED_BY]-(d:Decision {kep_path: $key})
WHERE size($kinds) = 0 OR d.kind IN $kinds
RETURN d AS decision, type(r) AS rel, x AS via, e.evidence_kind AS evidence_kind
ORDER BY d.decided_at DESC, d.key, x.key
LIMIT 50`;

export default function AboutPage() {
  return (
    <>
      <PageHeader
        eyebrow="About"
        title="What KEP Brain is"
        lead="A company brain for the Kubernetes enhancement process: every KEP, SIG, person, decision and record in one graph, read live from public GitHub, answered only with evidence."
      />
      <div className="space-y-6">
        <Card title="What a KEP is" id="kep">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-3 text-fg-secondary">
              <p>
                A <strong className="text-fg">KEP</strong> is a <strong className="text-fg">Kubernetes Enhancement Proposal</strong>: the
                design document every significant change to Kubernetes goes through before code lands. It explains the
                motivation and design and the criteria for alpha, beta and stable. A KEP that changes kubernetes/kubernetes
                (in-tree) also passes a production readiness review (PRR); older or out-of-tree KEPs may have none.
              </p>
              <p>
                Each KEP is a folder in{" "}
                <ExtLink href={ENH} quiet={false}>
                  kubernetes/enhancements
                </ExtLink>{" "}
                with a README (the proposal) and a <span className="font-mono">kep.yaml</span> (status, stage, owning SIG,
                authors, approvers, target releases). It also has a tracking issue in the same repository, and{" "}
                <strong className="text-fg">the issue number is the KEP number</strong> since early 2019: KEP-4671 is issue #4671
                and the folder keps/sig-scheduling/4671-gang-scheduling. A few older KEPs carry a pull request number or none.
              </p>
              <p>
                The{" "}
                <ExtLink href={PROCESS_DOC} quiet={false}>
                  KEP process document
                </ExtLink>{" "}
                makes kep.yaml the record of a KEP&apos;s state, pairs <span className="font-mono">replaces</span> with{" "}
                <span className="font-mono">superseded-by</span> on the other KEP, and says the metadata exists to communicate
                status and to support tooling. KEP Brain stores that document too, so you can ask about the process itself.
              </p>
            </div>
            <table className={tableClass}>
              <caption className="sr-only">The seven kep.yaml statuses, as the process document defines them</caption>
              <thead>
                <tr>
                  <th className={thClass}>Status</th>
                  <th className={thClass}>Definition</th>
                </tr>
              </thead>
              <tbody>
                {STATUSES.map(([s, m]) => (
                  <tr key={s}>
                    <td className={`${tdClass} font-mono text-xs`}>{s}</td>
                    <td className={tdClass}>{m}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="What KEP Brain does" id="does">
          <ul className="grid gap-4 md:grid-cols-2">
            <li>
              <p className="font-semibold">
                <Link href="/ask" className="quiet-link">
                  Ask
                </Link>
              </p>
              <p className="mt-1 text-fg-secondary">
                Why a KEP is designed the way it is, who approved it and on what evidence, who knows an area, what changed
                since a release, whether a record is still current, and what a KEP or a status is. Every answer shows the
                graph path it read and cites the records behind it.
              </p>
            </li>
            <li>
              <p className="font-semibold">
                <Link href="/explore" className="quiet-link">
                  Explore
                </Link>
              </p>
              <p className="mt-1 text-fg-secondary">
                KEPs with facts, status history, derived decisions, lineage and findings; SIGs with leadership and their KEPs;
                people with their roles, what they author, review, approve and decide on.
              </p>
            </li>
            <li>
              <p className="font-semibold">
                <Link href="/audit" className="quiet-link">
                  Audit
                </Link>
              </p>
              <p className="mt-1 text-fg-secondary">
                Every pair of records that disagree, both sides linked to GitHub, who set each value, a suggested fix and a
                drafted issue text. Also what changed since a release, and the sync log.
              </p>
            </li>
            <li>
              <p className="font-semibold">
                <Link href="/tools" className="quiet-link">
                  Tools and MCP
                </Link>
              </p>
              <p className="mt-1 text-fg-secondary">
                The read-only graph tools behind every answer, callable directly with their parameters, and the same catalog
                served over the Model Context Protocol so other agents can query the graph.
              </p>
            </li>
          </ul>
        </Card>

        <Card title="Data sources and what is loaded" id="sources">
          <Suspense fallback={<SkeletonBlock lines={4} label="Loading data sources" />}>
            <Sources />
          </Suspense>
        </Card>

        <Card title="How the graph is built" id="graph">
          <ol className="max-w-[80ch] list-decimal space-y-2 pl-5 text-fg-secondary">
            <li>
              <strong className="text-fg">Ingest.</strong> The worker clones kubernetes/enhancements and kubernetes/community,
              reads OWNERS files from kubernetes/kubernetes through the GitHub API, and fetches tracking issues, timelines,
              pull requests and review threads for the SIGs in scope. Nothing ships pre-populated; every run upserts into the
              same graph, so re-running is safe.
            </li>
            <li>
              <strong className="text-fg">History, not snapshots.</strong> Every kep.yaml revision is replayed. State edges
              (owner, approver, tracked-by, targets, replaces…) carry the interval they were valid for, so &ldquo;current&rdquo;
              and &ldquo;as of release X&rdquo; are the same graph with a different filter. Edges that disappear from a source
              are closed, not deleted.
            </li>
            <li>
              <strong className="text-fg">Derive.</strong> Field changes become StatusChange nodes linked to their commit and
              pull request; Decision nodes are derived from them and linked to the people who decided and the evidence; the
              five checks below write Finding nodes; PageRank over decisions gives each person an influence score.
            </li>
            <li>
              <strong className="text-fg">Serve.</strong> The API reads the kep graph with read-only queries only; answers
              are cached in a separate ops graph, and your memory lives in a graph of its own. The web app,
              the answering agent and the MCP server all go through the same parameterised tool catalog. The browser talks
              only to this app&apos;s same-origin proxy.
            </li>
          </ol>
          <div className="mt-5">
            <TableWrap label="Node labels in the graph">
              <table className={tableClass}>
                <caption className="sr-only">Node labels in the graph</caption>
                <thead>
                  <tr>
                    <th className={thClass}>Nodes</th>
                    <th className={thClass}>What they hold</th>
                  </tr>
                </thead>
                <tbody>
                  {NODES.map(([n, d]) => (
                    <tr key={n}>
                      <td className={`${tdClass} font-mono text-xs`}>{n}</td>
                      <td className={tdClass}>{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </div>
        </Card>

        <Card title="Why a graph" id="why-graph">
          <div className="max-w-[80ch] space-y-3 text-fg-secondary">
            <p>
              &ldquo;Did this person take part in a decision on this KEP, and where?&rdquo; crosses three records: the person,
              the review or comment they wrote, and the decision that cites it as evidence. A vector store finds similar text
              but cannot follow who wrote what and what cites it; in SQL each hop is another join through link tables. In the
              graph it is one pattern, and the tool behind it runs this query as written:
            </p>
            <pre className="overflow-x-auto rounded-sm border border-border bg-surface-subtle p-3 font-mono text-xs text-fg">
              <code>{DECISION_EVIDENCE_QUERY}</code>
            </pre>
            <p>
              Longer connections, such as how a person reaches a KEP through other KEPs and SIGs, use the database&apos;s
              shortest-path search over the same edges, up to four hops.
            </p>
          </div>
        </Card>

        <Card title="Indexes and constraints" id="indexes">
          <Suspense fallback={<SkeletonBlock lines={4} label="Loading indexes" />}>
            <Schema />
          </Suspense>
        </Card>

        <Card title="How an answer is produced, and when there is none" id="answers">
          <ol className="max-w-[80ch] list-decimal space-y-2 pl-5 text-fg-secondary">
            <li>The question goes to a language model that may only call the read-only graph tools, in at most three rounds.</li>
            <li>
              Every tool result is a set of graph records, each with an evidence id and a public GitHub URL. The model writes
              its answer with those ids as inline citations.
            </li>
            <li>
              A validator checks every citation against the records actually returned in that request. An answer with a
              citation it cannot tie to a record, or with none at all, is replaced by an abstention. Plain mentions of a
              returned KEP, issue or person are linked to that record.
            </li>
            <li>
              Abstention reasons: <span className="font-mono">no_evidence</span> (the graph holds nothing relevant),{" "}
              <span className="font-mono">out_of_scope</span> (not about KEPs, the process, the loaded SIGs or KEP Brain itself),{" "}
              <span className="font-mono">unsupported_claims</span> (a citation did not match the records returned, or there was none),{" "}
              <span className="font-mono">budget_exhausted</span> (the answering budget ran out before an answer was checked),{" "}
              <span className="font-mono">graph_unavailable</span> (the graph database did not answer).
            </li>
            <li>
              Answers are cached per question and graph version. A per-browser memory id lets the model recall your earlier
              questions; it can be inspected and deleted under <Link href="/memory" className="quiet-link">Memory</Link>.
            </li>
          </ol>
        </Card>

        <Card title="The five checks behind the audit" id="checks">
          <TableWrap label="Finding kinds">
            <table className={tableClass}>
              <caption className="sr-only">Finding kinds and their meaning</caption>
              <thead>
                <tr>
                  <th className={thClass}>Check</th>
                  <th className={thClass}>What it means</th>
                </tr>
              </thead>
              <tbody>
                {KINDS.map((k) => (
                  <tr key={k}>
                    <td className={tdClass}>
                      {humanize(k)}
                      <span className="block font-mono text-xs text-fg-muted [overflow-wrap:anywhere]">{k}</span>
                    </td>
                    <td className={tdClass}>{FINDING_KIND_TEXT[k]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <p className="mt-3 max-w-[80ch] text-sm text-fg-secondary">
            Each finding keeps both records with their source URLs, the people who set each value, a suggested fix and a
            lifecycle (open, triaged, drafted, confirmed, dismissed, resolved upstream). The audit page reports how many
            findings have been hand-checked; recall is not measured because there is no complete list of disagreements to
            compare against.
          </p>
        </Card>

        <Card title="Scope and limits" id="scope">
          <ul className="max-w-[80ch] list-disc space-y-2 pl-5 text-fg-secondary">
            <li>
              Only the SIGs listed under data sources are loaded. Other SIGs appear on the explore page as &ldquo;not
              loaded&rdquo; and have no KEP data behind them. Widening scope is a configuration change and a worker run.
            </li>
            <li>The data is as fresh as the last worker run; the date and commit are shown in the top bar on every page.</li>
            <li>
              Answers cite records in the graph. Fixes are drafted for a human to review, with read-only access to
              GitHub. People are stored by public GitHub login only.
            </li>
            <li>
              A long list is shown in full on the explore and audit pages; in an answer, the model sees a bounded slice and
              must say how many records are not shown.
            </li>
          </ul>
        </Card>

        <Card title="Licences" id="licences">
          <ul className="max-w-[80ch] list-disc space-y-2 pl-5 text-fg-secondary">
            <li>
              <strong className="text-fg">Code: MIT.</strong> KEP Brain itself is open source under the MIT licence; see the{" "}
              <ExtLink href={`${REPO}/blob/main/LICENSE`} quiet={false}>
                LICENSE file
              </ExtLink>{" "}
              in its repository. It is provided as is, without warranty of any kind.
            </li>
            <li>
              <strong className="text-fg">Data: Apache-2.0.</strong> KEP texts, metadata and issues are written by The
              Kubernetes Authors and published under the{" "}
              <ExtLink href={`${ENH}/blob/master/LICENSE`} quiet={false}>
                Apache License 2.0
              </ExtLink>
              . KEP Brain reads them in place and links back to them; it changes nothing upstream.
            </li>
            <li>
              <strong className="text-fg">Terms.</strong> The software and this site are provided as is, without warranty of
              any kind. The data is read from public GitHub sources published under Apache-2.0 and is shown as recorded there.
            </li>
            <li>
              <strong className="text-fg">Fonts and icons.</strong> Geist and Geist Mono are used under the SIL Open Font
              License 1.1 and served from this site, not from a font network. Icons are Lucide, under the ISC licence. The
              mark and the screenshots are the project&apos;s own.
            </li>
            <li>
              Kubernetes is a trademark of The Linux Foundation. KEP Brain is an independent open-source project by one
              developer and is not affiliated with, or endorsed by, the Kubernetes project, the CNCF or FalkorDB.
            </li>
          </ul>
        </Card>

        <Card title="Privacy and your data" id="privacy">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-3 text-fg-secondary">
              <p>
                <strong className="text-fg">No account, no cookies, no tracking.</strong> KEP Brain sets no cookies and
                loads no analytics, advertising or other third-party script, so there is no consent banner because there is
                nothing to consent to. Pages make requests only to this site&apos;s own API.
              </p>
              <p>
                <strong className="text-fg">What your browser keeps.</strong> Three values in local storage: your theme
                choice, an anonymous memory id generated in your browser, and whether the evidence chain keeps several
                branches open. None of them identifies you; clearing site data removes all three.
              </p>
              <p>
                <strong className="text-fg">What leaves your browser.</strong> The text of a question is sent to the API with
                your memory id. The API sends the question and the graph rows it read to the model provider named in the
                footer to compose the answer; that provider&apos;s own terms govern what it retains.
              </p>
            </div>
            <div className="space-y-3 text-fg-secondary">
              <p>
                <strong className="text-fg">What the server keeps.</strong> Only what the <Link href="/memory" className="quiet-link">Memory</Link>{" "}
                page shows you: per memory id, each answered question, a 300-character answer summary, the record keys it
                cited, the KEP, SIG and release names found in the question, the sequence of tools used, and timestamps.
                This is kept in a graph of its own, so no other visitor can read it, and the API does not write question
                text to its logs.
              </p>
              <p>
                <strong className="text-fg">Deleting your data.</strong> &ldquo;Forget everything&rdquo; on the Memory page
                deletes that whole graph at once, and &ldquo;New identity&rdquo; starts a fresh id; the API also deletes
                single facts and playbooks. There is nothing else to request, because nothing else about you is stored.
              </p>
              <p>
                <strong className="text-fg">People in the graph.</strong> The graph holds public GitHub logins and the public
                roles they hold: author, reviewer and approver from kep.yaml in kubernetes/enhancements, chair and tech lead
                from sigs.yaml in kubernetes/community, and OWNERS roles from kubernetes/kubernetes. E-mail addresses are never
                ingested. The service is free, has no paid tier and sends no e-mail. It is not directed at children and
                collects no personal data beyond the questions you choose to type.
              </p>
            </div>
          </div>
        </Card>

        <Card title="Accessibility" id="accessibility">
          <ul className="max-w-[80ch] list-disc space-y-2 pl-5 text-fg-secondary">
            <li>
              <strong className="text-fg">Keyboard.</strong> Every action is reachable without a mouse: a skip link, roving
              focus in the tabs, ARIA comboboxes for both searches, focusable finding rows, and the shortcuts below. The
              focus ring is visible in both themes.
            </li>
            <li>
              <strong className="text-fg">Contrast.</strong> Every text colour in the palette was measured against each
              surface it is used on; the lowest ratio is 4.52:1 in the light theme and 4.50:1 in the dark theme, at or above
              the WCAG AA minimum of 4.5:1. Chart fills carry text labels and legends, so colour is never the only cue.
            </li>
            <li>
              <strong className="text-fg">Structure.</strong> One heading per section, tables with captions and column
              headers, decorative icons hidden from screen readers, live regions for search and answer status, and a page
              title and description on every route.
            </li>
            <li>
              Found something that does not work with your assistive technology? Open an issue in the{" "}
              <ExtLink href={`${REPO}/issues`} quiet={false}>
                repository
              </ExtLink>
              .
            </li>
          </ul>
        </Card>

        <Card title="Keyboard shortcuts" id="shortcut-list">
          <p className="mb-4 max-w-[80ch] text-fg-secondary">
            Press <kbd>?</kbd> on any page for this list. Single-letter shortcuts pause while you type in a field.
          </p>
          <div className="grid gap-x-8 gap-y-6 md:grid-cols-2">
            {SHORTCUT_GROUPS.map((g) => (
              <table key={g.title} className={tableClass}>
                <caption className="pb-1 text-left">
                  <span className="eyebrow">{g.title}</span>
                  {g.where ? <span className="ml-2 text-xs text-fg-muted">{g.where}</span> : null}
                </caption>
                <thead className="sr-only">
                  <tr>
                    <th className={thClass}>Key</th>
                    <th className={thClass}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {g.items.map((it) => (
                    <tr key={it.action}>
                      <td className={cx(tdClass, "w-36 whitespace-nowrap")}>
                        <Keys keys={it.keys} />
                      </td>
                      <td className={tdClass}>{it.action}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}

async function Sources() {
  const res = await serverApi.meta();
  if (!res.ok) return <ErrorState error={res.error} what="Data sources" />;
  const m = res.data;
  const g = m.graph;
  return (
    <div className="space-y-4">
      <p className="max-w-[80ch] text-fg-secondary">
        Data snapshot: issues as of{" "}
        <span className="font-mono text-fg">{m.sources.tickets_as_of ? isoUtc(m.sources.tickets_as_of) : "not synced yet"}</span>, enhancements{" "}
        <span className="font-mono text-fg">{m.sources.enhancements_sha ? shortSha(m.sources.enhancements_sha) : "not recorded"}</span>.
      </p>
      <Facts
        items={[
          {
            label: "kubernetes/enhancements",
            value: m.sources.enhancements_sha ? (
              <ExtLink href={`${ENH}/tree/${m.sources.enhancements_sha}`}>
                <span className="font-mono break-all">{m.sources.enhancements_sha}</span>
              </ExtLink>
            ) : (
              <span className="text-fg-secondary">not recorded</span>
            ),
          },
          {
            label: "kubernetes/community (sigs.yaml)",
            value: m.sources.community_sha ? (
              <ExtLink href={`https://github.com/kubernetes/community/tree/${m.sources.community_sha}`}>
                <span className="font-mono break-all">{m.sources.community_sha}</span>
              </ExtLink>
            ) : (
              <span className="text-fg-secondary">not recorded</span>
            ),
          },
          {
            label: "Issues and pull requests as of",
            value: m.sources.tickets_as_of ? <span className="font-mono">{m.sources.tickets_as_of}</span> : <span className="text-fg-secondary">not synced yet</span>,
          },
          { label: "Loaded SIGs", value: <span className="font-mono">{m.sigs.join(", ") || "none"}</span> },
          { label: "Graph database", value: <span className="font-mono">{m.falkordb_image ?? "not reported"}</span> },
          {
            label: "Language model",
            value: m.llm.configured ? (
              <span className="font-mono">
                {m.llm.provider} {m.llm.model}
              </span>
            ) : (
              <span className="text-fg-secondary">not configured; Audit and the KEP pages still work</span>
            ),
          },
        ]}
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatTile label="Nodes" value={g.nodes.toLocaleString("en-US")} />
        <StatTile label="Edges" value={g.edges.toLocaleString("en-US")} />
        <StatTile label="KEPs" value={g.keps.toLocaleString("en-US")} />
        <StatTile label="Findings" value={g.findings.toLocaleString("en-US")} />
        <StatTile label="People" value={g.people.toLocaleString("en-US")} />
      </div>
    </div>
  );
}

interface IndexRow {
  label?: unknown;
  properties?: unknown;
  types?: unknown;
}

interface ConstraintRow {
  type?: unknown;
  label?: unknown;
  properties?: unknown;
  entitytype?: unknown;
  status?: unknown;
}

function strings(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : typeof v === "string" ? [v] : [];
}

/** One line per label and index type, with the indexed properties: `types` maps each property to its index types. */
function indexLines(rows: IndexRow[]): { label: string; type: string; props: string[] }[] {
  const out = new Map<string, { label: string; type: string; props: string[] }>();
  for (const r of rows) {
    const label = String(r.label ?? "");
    if (!label) continue;
    const types = typeof r.types === "object" && r.types !== null && !Array.isArray(r.types) ? (r.types as Record<string, unknown>) : {};
    const props = Object.keys(types).length ? Object.keys(types) : strings(r.properties);
    for (const prop of props) {
      for (const t of strings(types[prop]).length ? strings(types[prop]) : ["RANGE"]) {
        const id = `${label}|${t}`;
        const line = out.get(id) ?? { label, type: t, props: [] };
        if (!line.props.includes(prop)) line.props.push(prop);
        out.set(id, line);
      }
    }
  }
  return [...out.values()].sort((a, b) => a.label.localeCompare(b.label) || a.type.localeCompare(b.type));
}

async function Schema() {
  const res = await serverApi.runTool("get_graph_schema", {});
  const row = res.ok ? (res.data.rows[0] as { indexes?: unknown; constraints?: unknown } | undefined) : undefined;
  if (!row || !Array.isArray(row.indexes)) {
    return <p className="text-sm text-fg-muted">The live index list is not available right now.</p>;
  }
  const lines = indexLines(row.indexes as IndexRow[]);
  const constraints = Array.isArray(row.constraints) ? (row.constraints as ConstraintRow[]) : null;
  return (
    <div className="space-y-5">
      <p className="max-w-[80ch] text-fg-secondary">
        Read from the graph database when this page loads: every lookup by key, number, status or date uses a range index,
        and search uses the full-text ones.
      </p>
      <TableWrap label="Indexes">
        <table className={tableClass}>
          <caption className="mb-1 text-left text-xs text-fg-muted">Indexes, {lines.length} by label and type</caption>
          <thead>
            <tr>
              <th className={thClass}>Label</th>
              <th className={thClass}>Type</th>
              <th className={thClass}>Properties</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={`${l.label}-${l.type}`}>
                <td className={cx(tdClass, "font-mono text-xs")}>{l.label}</td>
                <td className={cx(tdClass, "font-mono text-xs")}>{l.type.toLowerCase()}</td>
                <td className={cx(tdClass, "font-mono text-xs [overflow-wrap:anywhere]")}>{l.props.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      {constraints && constraints.length > 0 ? (
        <TableWrap label="Constraints">
          <table className={tableClass}>
            <caption className="mb-1 text-left text-xs text-fg-muted">Constraints, {constraints.length}</caption>
            <thead>
              <tr>
                <th className={thClass}>Label</th>
                <th className={thClass}>Type</th>
                <th className={thClass}>Properties</th>
                <th className={thClass}>Status</th>
              </tr>
            </thead>
            <tbody>
              {constraints.map((c, i) => (
                <tr key={`${String(c.label)}-${String(c.type)}-${strings(c.properties).join(",")}-${i}`}>
                  <td className={cx(tdClass, "font-mono text-xs")}>{String(c.label ?? "")}</td>
                  <td className={cx(tdClass, "font-mono text-xs")}>{String(c.type ?? "").toLowerCase()}</td>
                  <td className={cx(tdClass, "font-mono text-xs [overflow-wrap:anywhere]")}>{strings(c.properties).join(", ")}</td>
                  <td className={cx(tdClass, "font-mono text-xs")}>{String(c.status ?? "").toLowerCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : constraints ? null : (
        <p className="text-sm text-fg-muted">The constraint list is not available right now.</p>
      )}
    </div>
  );
}
