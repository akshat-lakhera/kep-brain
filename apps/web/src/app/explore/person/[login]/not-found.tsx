import Link from "next/link";
import type { Route } from "next";
import { serverApi } from "@/lib/api/server";

export default async function PersonNotFound() {
  const meta = await serverApi.meta();
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">This login is not in the graph</h1>
      <p className="text-fg-secondary">
        {meta.ok ? (
          <>
            The graph holds {meta.data.graph.people.toLocaleString("en-US")} people from kep.yaml, PRR files, sigs.yaml, OWNERS files and
            tracking-issue events in the loaded SIGs (<span className="font-mono">{meta.data.sigs.join(", ")}</span>).
          </>
        ) : (
          "The API did not report which SIGs are loaded."
        )}{" "}
        A login appears only when it authored, reviewed, approved or decided on a loaded KEP.
      </p>
      <Link href={"/explore" as Route} className="quiet-link">
        Back to Explore
      </Link>
    </div>
  );
}
