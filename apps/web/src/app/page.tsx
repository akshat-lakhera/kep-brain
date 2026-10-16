import { Suspense } from "react";
import { AskClient } from "@/components/AskClient";
import { FindingsChain } from "@/components/FindingsChain";
import { EntryPoints } from "@/components/EntryPoints";
import { InstrumentStrip } from "@/components/InstrumentStrip";
import { EmptyState, ErrorState, SkeletonBlock } from "@/components/ui";
import { serverApi } from "@/lib/api/server";

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

  return (
    <div className="space-y-6">
      {meta.ok ? <InstrumentStrip meta={meta.data} /> : <ErrorState error={meta.error} what="Graph status" />}
      <AskClient meta={meta.ok ? meta.data : null} findings={findings.ok ? findings.data.items : []} idle={idle} />
    </div>
  );
}
