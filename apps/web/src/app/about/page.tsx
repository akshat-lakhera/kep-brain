import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import { FINDING_KIND_TEXT, humanize } from "@/lib/format";
import { Card, ErrorState, ExtLink, Facts, PageHeader, SkeletonBlock, StatTile, tableClass, tdClass, thClass } from "@/components/ui";

export const metadata: Metadata = {
  title: "About",
  description:
    "What a KEP is, what KEP Brain reads, how the graph is built, how answers are produced and checked, the five audit checks, scope, licences and privacy.",
};

const ENH = "https://github.com/kubernetes/enhancements";
const PROCESS_DOC = `${ENH}/blob/master/keps/sig-architecture/0000-kep-process/README.md`;

const STATUSES: [string, string][] = [
  ["provisional", "accepted as an idea; design not yet agreed"],
  ["implementable", "design approved; work may start or is under way"],
  ["implemented", "shipped; the enhancement is done"],
  ["deferred", "parked for a later release"],
  ["rejected", "declined"],
  ["withdrawn", "pulled by its authors"],
  ["replaced", "superseded by another KEP, listed in superseded-by"],
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

const SHORTCUTS: [string, string][] = [
  ["/", "Focus the question box"],
  ["Enter", "Send the question"],
  ["Shift+Enter", "New line in the question"],
  ["Escape", "Cancel a running question"],
  ["Ctrl+K", "Focus KEP search"],
  ["Enter or click on a finding row", "Expand the finding"],
  ["d on a focused finding row", "Draft the fix"],
];

export default function AboutPage() {
  return (
    <>
      <PageHeader
        eyebrow="About"
        title="What KEP Brain is, and what it is not"
        lead="A company brain for the Kubernetes enhancement process: every KEP, SIG, person, decision and record in one graph, read live from public GitHub, answered only with evidence."
      />
      <div className="space-y-6">
        <Card title="What a KEP is" id="kep">
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-3 text-fg-secondary">
              <p>
                A <strong className="text-fg">KEP</strong> is a <strong className="text-fg">Kubernetes Enhancement Proposal</strong>: the
                design document every significant change to Kubernetes goes through before code lands. It explains the
                motivation and design, the criteria for alpha, beta and stable, and passes a production readiness review
                (PRR).
              </p>
              <p>
                Each KEP is a folder in{" "}
                <ExtLink href={ENH} quiet={false}>
                  kubernetes/enhancements
                </ExtLink>{" "}
                with a README (the proposal) and a <span className="font-mono">kep.yaml</span> (status, stage, owning SIG,
                authors, approvers, target releases). It also has a tracking issue in the same repository, and{" "}
                <strong className="text-fg">the issue number is the KEP number</strong>: KEP-4671 is issue #4671 and the folder
                keps/sig-scheduling/4671-gang-scheduling.
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
              <caption className="sr-only">The seven kep.yaml statuses</caption>
              <thead>
                <tr>
                  <th className={thClass}>Status</th>
                  <th className={thClass}>Meaning</th>
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
                graph path it read and cites each claim.
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
              <strong className="text-fg">Serve.</strong> The API reads the graph with read-only queries only. The web app,
              the answering agent and the MCP server all go through the same parameterised tool catalog. The browser talks
              only to this app&apos;s same-origin proxy.
            </li>
          </ol>
          <table className={`${tableClass} mt-5`}>
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
                  <td className={`${tdClass} font-mono text-xs whitespace-nowrap`}>{n}</td>
                  <td className={tdClass}>{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="How an answer is produced, and when there is none" id="answers">
          <ol className="max-w-[80ch] list-decimal space-y-2 pl-5 text-fg-secondary">
            <li>The question goes to a language model that may only call the read-only graph tools, in at most three rounds.</li>
            <li>
              Every tool result is a set of graph records, each with an evidence id and a public GitHub URL. The model writes
              its answer with those ids after every claim.
            </li>
            <li>
              A validator checks every claim against the records actually returned in that request. A claim it cannot tie to
              a record is unsupported; if any remain, the whole answer is replaced by an abstention.
            </li>
            <li>
              Abstention reasons: <span className="font-mono">no_evidence</span> (the graph holds nothing relevant),{" "}
              <span className="font-mono">out_of_scope</span> (not about KEPs, the process or the loaded SIGs),{" "}
              <span className="font-mono">unsupported_claims</span> (the model wrote something the records do not back).
            </li>
            <li>
              Answers are cached per question and graph version. A per-browser memory id lets the model recall your earlier
              questions; it can be inspected and deleted under <Link href="/memory" className="quiet-link">Memory</Link>.
            </li>
          </ol>
        </Card>

        <Card title="The five checks behind the audit" id="checks">
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
                  <td className={`${tdClass} whitespace-nowrap`}>
                    {humanize(k)}
                    <span className="block font-mono text-xs text-fg-muted">{k}</span>
                  </td>
                  <td className={tdClass}>{FINDING_KIND_TEXT[k]}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
            <li>It never answers from outside knowledge, never writes to GitHub, and never stores e-mail addresses.</li>
            <li>
              A long list is shown in full on the explore and audit pages; in an answer, the model sees a bounded slice and
              must say how many records are not shown.
            </li>
          </ul>
        </Card>

        <Card title="Licences and privacy" id="licences">
          <ul className="max-w-[80ch] list-disc space-y-2 pl-5 text-fg-secondary">
            <li>
              <strong className="text-fg">Code: MIT.</strong> KEP Brain itself is open source under the MIT licence; see the
              LICENSE file in its repository.
            </li>
            <li>
              <strong className="text-fg">Data: Apache-2.0.</strong> KEP texts, metadata and issues are written by The
              Kubernetes Authors and published under the{" "}
              <ExtLink href={`${ENH}/blob/master/LICENSE`} quiet={false}>
                Apache License 2.0
              </ExtLink>
              . KEP Brain reads them in place and links back to them.
            </li>
            <li>Only public GitHub logins are stored for people; e-mail addresses are never ingested.</li>
            <li>
              The browser stores three things: the theme choice, an anonymous memory id and whether the evidence chain keeps
              several branches open. Your questions are never shown to other visitors.
            </li>
          </ul>
        </Card>

        <Card title="Keyboard shortcuts" id="shortcuts">
          <table className={tableClass}>
            <caption className="sr-only">Keyboard shortcuts</caption>
            <thead>
              <tr>
                <th className={thClass}>Key</th>
                <th className={thClass}>Action</th>
              </tr>
            </thead>
            <tbody>
              {SHORTCUTS.map(([k, a]) => (
                <tr key={k}>
                  <td className={tdClass}>
                    <kbd className="rounded-sm border border-border bg-surface-subtle px-1 font-mono text-xs">{k}</kbd>
                  </td>
                  <td className={tdClass}>{a}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
