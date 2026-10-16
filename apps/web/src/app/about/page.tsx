import type { Metadata } from "next";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import { Card, ErrorState, ExtLink, Facts, PageHeader, SkeletonBlock, StatTile, tableClass, tdClass, thClass } from "@/components/ui";

export const metadata: Metadata = { title: "About" };

const SHORTCUTS: [string, string][] = [
  ["/", "Focus the question box"],
  ["Enter", "Send the question"],
  ["Shift+Enter", "New line in the question"],
  ["Escape", "Cancel a running question"],
  ["Ctrl+K", "Focus KEP search"],
];

export default function AboutPage() {
  return (
    <>
      <PageHeader
        title="About KEP Brain"
        lead="KEP Brain audits Kubernetes decision records: it finds where KEP metadata, tracking issues and replacement declarations disagree, shows who decided each state and the evidence, and drafts the fix."
      />
      <div className="space-y-6">
        <Card title="Data sources" id="sources">
          <Suspense fallback={<SkeletonBlock lines={4} label="Loading data sources" />}>
            <Sources />
          </Suspense>
        </Card>

        <Card title="How it works">
          <ol className="max-w-[80ch] list-decimal space-y-2 pl-5">
            <li>
              kep.yaml, README sections and PRR files are read from a pinned clone of kubernetes/enhancements; tracking
              issues and pull requests from the GitHub API. Everything is stored as a property graph in FalkorDB.
            </li>
            <li>
              Cypher predicates compare two independently sourced records about the same KEP and write a Finding node
              where they disagree. Decisions are derived from merged status changes and the people on them.
            </li>
            <li>
              Ask runs a tool-calling agent; every tool is a parameterised Cypher query. Each claim must cite a graph
              node with a public GitHub URL, or the agent abstains.
            </li>
            <li>The browser talks only to this app&apos;s same-origin proxy of the KEP Brain API.</li>
          </ol>
        </Card>

        <Card title="Licences and privacy">
          <ul className="max-w-[80ch] list-disc space-y-2 pl-5">
            <li>
              KEP texts, metadata and issues are written by The Kubernetes Authors and published under the{" "}
              <ExtLink href="https://github.com/kubernetes/enhancements/blob/master/LICENSE" quiet={false}>
                Apache License 2.0
              </ExtLink>
              .
            </li>
            <li>Only public GitHub logins are stored for people; e-mail addresses are never ingested.</li>
            <li>
              The browser stores three things: the theme choice, an anonymous memory id and whether the evidence chain keeps
              several branches open. Your questions are never shown
              to other visitors.
            </li>
          </ul>
        </Card>

        <Card title="Keyboard shortcuts">
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
              <ExtLink href={`https://github.com/kubernetes/enhancements/tree/${m.sources.enhancements_sha}`}>
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
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <StatTile label="Nodes" value={g.nodes.toLocaleString("en-US")} />
        <StatTile label="Edges" value={g.edges.toLocaleString("en-US")} />
        <StatTile label="KEPs" value={g.keps.toLocaleString("en-US")} />
        <StatTile label="Findings" value={g.findings.toLocaleString("en-US")} />
        <StatTile label="People" value={g.people.toLocaleString("en-US")} />
      </div>
    </div>
  );
}
