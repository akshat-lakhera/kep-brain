import { Suspense } from "react";
import { AskClient } from "@/components/AskClient";
import { SkeletonBlock } from "@/components/ui";
import { serverApi } from "@/lib/api/server";

export default function AskPage() {
  return (
    <>
      <h1 className="sr-only">Ask KEP Brain</h1>
      <Suspense fallback={<SkeletonBlock lines={4} label="Loading the question box" />}>
        <Ask />
      </Suspense>
    </>
  );
}

async function Ask() {
  const meta = await serverApi.meta();
  return <AskClient sigs={meta.ok ? meta.data.sigs : null} />;
}
