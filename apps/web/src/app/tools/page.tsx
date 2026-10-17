import type { Metadata } from "next";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import { ToolsClient } from "@/components/ToolsClient";
import { EmptyState, ErrorState, PageHeader, SkeletonBlock } from "@/components/ui";

export const metadata: Metadata = {
  title: "Tools",
  description: "The read-only graph tools behind every answer, callable directly with their parameters.",
};

export default function ToolsPage() {
  return (
    <>
      <PageHeader
        title="Tools"
        lead="The read-only graph tools the answering agent and the MCP server call, run directly. Pick a tool, fill its parameters, and read the Cypher template, the rows, the evidence records and the traversed paths it returns. No language model is involved."
      />
      <Suspense fallback={<ToolsSkeleton />}>
        <ToolsBody />
      </Suspense>
    </>
  );
}

function ToolsSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-12">
      <div className="lg:col-span-3">
        <SkeletonBlock lines={8} label="Loading the tool list" />
      </div>
      <div className="lg:col-span-9">
        <div className="skeleton h-48 w-full" />
      </div>
    </div>
  );
}

async function ToolsBody() {
  const res = await serverApi.tools();
  if (!res.ok) return <ErrorState error={res.error} what="Tools" />;
  if (res.data.items.length === 0) {
    return (
      <EmptyState title="The API lists no tools">
        <span className="font-mono">GET /v1/tools</span> returned an empty list: the tool registry has nothing registered, so there is nothing to run.
      </EmptyState>
    );
  }
  return <ToolsClient tools={res.data.items} />;
}
