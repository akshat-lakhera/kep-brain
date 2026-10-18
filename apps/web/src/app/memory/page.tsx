import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";
import { MemoryClient } from "@/components/MemoryClient";
import { PageHeader } from "@/components/ui";

export const metadata: Metadata = {
  title: "Memory",
  description: "What KEP Brain remembers for this browser, and how to inspect or delete it.",
  alternates: { canonical: "/memory" },
  robots: { index: false },
};

/**
 * This page has no server data of its own, so without this marker it would be prerendered while the layout's metadata
 * (which reads the deployment's base URL per request) cannot be; rendering it per request keeps the two consistent.
 */
async function PerRequest() {
  await connection();
  return null;
}

export default function MemoryPage() {
  return (
    <>
      <Suspense fallback={null}>
        <PerRequest />
      </Suspense>
      <PageHeader
        title="Memory"
        lead="What this browser's questions have taught KEP Brain, under an anonymous id you can reset or delete. It fills as you ask; shared findings and the task queue are the agents' own state."
      />
      <MemoryClient />
    </>
  );
}
