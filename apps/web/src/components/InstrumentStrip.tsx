import Link from "next/link";
import type { ReactNode } from "react";
import type { Meta } from "@/lib/api/types";
import { isoUtc, shortSha } from "@/lib/format";
import { releaseNames } from "@/lib/releases";
import { ExtLink, SigLink } from "./ui";

/** One reading of the strip: a small label, then the value, separated from its neighbours by a hairline. */
function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline gap-2 border-l border-border pl-4 first:border-l-0 first:pl-0">
      <dt className="shrink-0 text-xs text-fg-muted">{label}</dt>
      <dd className="min-w-0 break-words text-sm text-fg-secondary">{children}</dd>
    </div>
  );
}

function Num({ value }: { value: number }) {
  return <span className="tabular font-medium text-fg">{value.toLocaleString("en-US")}</span>;
}

/** What the brain holds and how current it is, every value from GET /v1/meta, as one quiet line under the ask box. */
export function InstrumentStrip({ meta }: { meta: Meta }) {
  const { graph, sources, sigs } = meta;
  const releases = releaseNames(meta.releases);
  return (
    <dl aria-label="What the graph holds" className="flex flex-wrap gap-x-4 gap-y-2 px-1">
      <Cell label="Nodes">
        <Num value={graph.nodes} />
      </Cell>
      <Cell label="Edges">
        <Num value={graph.edges} />
      </Cell>
      <Cell label="KEPs">
        <Num value={graph.keps} />
      </Cell>
      <Cell label="People">
        <Num value={graph.people} />
      </Cell>
      <Cell label="Disagree">
        <Link href="/audit" className="quiet-link">
          <Num value={graph.findings} /> findings
        </Link>
      </Cell>
      <Cell label="As of">
        {sources.enhancements_sha ? (
          <ExtLink
            href={`https://github.com/kubernetes/enhancements/tree/${sources.enhancements_sha}`}
            label={`kubernetes/enhancements at ${sources.enhancements_sha}`}
          >
            <span className="ident">enhancements@{shortSha(sources.enhancements_sha)}</span>
          </ExtLink>
        ) : (
          <span className="text-fg-muted">enhancements commit not reported</span>
        )}
        <span className="ident ml-2 text-xs text-fg-muted">
          {sources.tickets_as_of ? `issues ${isoUtc(sources.tickets_as_of)}` : "issue snapshot time not reported"}
        </span>
      </Cell>
      <Cell label="SIGs">
        <span className="flex flex-wrap gap-x-2">
          {sigs.length ? sigs.map((s) => <SigLink key={s} sig={s} />) : <span className="text-fg-muted">none reported</span>}
          {releases.length ? (
            <span className="ident text-xs text-fg-muted">
              {releases.length} releases, {releases[0]} to {releases[releases.length - 1]}
            </span>
          ) : null}
        </span>
      </Cell>
    </dl>
  );
}
