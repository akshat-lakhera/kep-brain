import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { AskClient } from "@/components/AskClient";
import { FindingsChain } from "@/components/FindingsChain";
import { EntryPoints } from "@/components/EntryPoints";
import { InstrumentStrip } from "@/components/InstrumentStrip";
import { EmptyState, ErrorState, SkeletonBlock } from "@/components/ui";
import { serverApi } from "@/lib/api/server";

export const metadata: Metadata = {
  title: "Ask",
  description: "Ask why a Kubernetes KEP is designed the way it is, who decided and on what evidence, who owns and knows it, and whether its record is current.",
};

export default function AskPage() {
  return (
    <>
      <h1 className="sr-only">Ask KEP Brain</h1>
      <Suspense
        fallback={
          <div className="space-y-6">
            <div className="skeleton h-16 w-full" />
            <div className="skeleton h-32 w-full" />
            <SkeletonBlock lines={6} label="Loading" />
          </div>
        }
      >
        <Home />
      </Suspense>
    </>
  );
}

async function Home() {
  const [meta, findings, changes, sigs] = await Promise.all([
    serverApi.meta(),
    serverApi.findings({}),
    serverApi.changes(),
    serverApi.sigs(),
  ]);

  const map = !findings.ok ? (
    <ErrorState error={findings.error} what="Findings map" />
  ) : findings.data.items.length === 0 ? (
    <EmptyState title="No records disagree">
      The graph holds no Finding nodes: the detector has not run on this graph, or every kep.yaml agrees with its tracking issue
      and replacement declarations.
    </EmptyState>
  ) : (
    <FindingsChain
      items={findings.data.items}
      summary={findings.data.summary}
      sigOrder={meta.ok ? meta.data.sigs : []}
      sha={meta.ok ? meta.data.sources.enhancements_sha : null}
    />
  );

  const idle = (
    <div className="space-y-6">
      <EntryPoints
        changes={changes}
        sigs={sigs}
        metaSigs={meta.ok ? meta.data.sigs : []}
        findings={findings.ok ? findings.data.items : []}
        summary={findings.ok ? findings.data.summary : null}
      />
      {map}
    </div>
  );

  if (meta.ok && meta.data.graph.keps === 0) {
    return (
      <EmptyState title="The graph is empty">
        <p>
          Nothing has been loaded yet. Run the worker to ingest the SIGs in scope, then reload this page:
        </p>
        <pre className="mt-2 overflow-x-auto rounded-sm bg-surface p-3 font-mono text-xs">docker compose run --rm worker all</pre>
        <p className="mt-2">
          The first run clones the public Kubernetes repositories and takes a while. Progress is visible under{" "}
          <Link href="/audit?tab=sync" className="quiet-link">
            Audit → Sync
          </Link>
          .
        </p>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      {meta.ok ? <InstrumentStrip meta={meta.data} /> : <ErrorState error={meta.error} what="Graph status" />}
      <AskClient meta={meta.ok ? meta.data : null} findings={findings.ok ? findings.data.items : []} idle={idle} />
    </div>
  );
}
