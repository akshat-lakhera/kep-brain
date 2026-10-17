import Link from "next/link";
import type { ReactNode } from "react";
import type { Meta } from "@/lib/api/types";
import { isoUtc, shortSha } from "@/lib/format";
import { releaseNames } from "@/lib/releases";
import { ExtLink, SigLink, cx } from "./ui";

/** One bento tile of the strip: eyebrow label over the value. */
function Cell({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={cx("min-w-0 rounded-md border border-border bg-surface px-3 py-2.5", className)}>
      <dt className="eyebrow">{label}</dt>
      <dd className="mt-1 min-w-0 break-words">{children}</dd>
    </div>
  );
}

function Num({ value }: { value: number }) {
  return <span className="display tabular text-xl font-semibold">{value.toLocaleString("en-US")}</span>;
}

/** What the brain holds and how current it is, every value from GET /v1/meta. */
export function InstrumentStrip({ meta }: { meta: Meta }) {
  const { graph, sources, sigs } = meta;
  const releases = releaseNames(meta.releases);
  return (
    <dl
      aria-label="What the graph holds"
      className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-[repeat(4,minmax(0,0.7fr))_repeat(3,minmax(0,1.2fr))]"
    >
      <Cell label="Graph nodes">
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
      <Cell label="Records that disagree">
        <Link href="/audit" className="quiet-link">
          <Num value={graph.findings} />
          <span className="ml-1 text-sm">findings</span>
        </Link>
      </Cell>
      <Cell label="Decision records as of">
        <span className="flex flex-col text-sm">
          {sources.enhancements_sha ? (
            <ExtLink href={`https://github.com/kubernetes/enhancements/tree/${sources.enhancements_sha}`} label={`kubernetes/enhancements at ${sources.enhancements_sha}`}>
              <span className="ident">enhancements@{shortSha(sources.enhancements_sha)}</span>
            </ExtLink>
          ) : (
            <span className="text-fg-muted">enhancements commit not reported</span>
          )}
          <span className="ident text-xs text-fg-muted">
            {sources.tickets_as_of ? `issues ${isoUtc(sources.tickets_as_of)}` : "issue snapshot time not reported"}
          </span>
        </span>
      </Cell>
      <Cell label={releases.length ? `SIGs loaded · ${releases.length} releases` : "SIGs loaded"} className="col-span-2 sm:col-span-2 xl:col-span-1">
        <span className="flex flex-col gap-0.5 text-sm">
          <span className="flex flex-wrap gap-x-2">
            {sigs.length ? sigs.map((s) => <SigLink key={s} sig={s} />) : <span className="text-fg-muted">none reported</span>}
          </span>
          {releases.length ? (
            <span className="ident text-xs text-fg-muted">
              {releases[0]} to {releases[releases.length - 1]}
            </span>
          ) : null}
        </span>
      </Cell>
    </dl>
  );
}
