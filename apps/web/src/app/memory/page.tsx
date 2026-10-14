import type { Metadata } from "next";
import { MemoryClient } from "@/components/MemoryClient";
import { PageHeader } from "@/components/ui";

export const metadata: Metadata = { title: "Memory" };

export default function MemoryPage() {
  return (
    <>
      <PageHeader
        title="Memory"
        lead="Your memory belongs to this browser's anonymous id. Shared findings are read by every agent. The task queue is coordination state, not memory."
      />
      <MemoryClient />
    </>
  );
}
