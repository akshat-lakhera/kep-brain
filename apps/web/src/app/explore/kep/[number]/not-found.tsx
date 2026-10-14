import Link from "next/link";
import { serverApi } from "@/lib/api/server";

export default async function KepNotFound() {
  const meta = await serverApi.meta();
  const sigs = meta.ok ? meta.data.sigs : [];
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">This KEP is not in the graph</h1>
      <p className="text-fg-secondary">
        {sigs.length ? (
          <>
            Loaded SIGs: <span className="font-mono">{sigs.join(", ")}</span>.
          </>
        ) : (
          "The API did not report which SIGs are loaded."
        )}{" "}
        Use the search in the top bar to find a KEP by number or title.
      </p>
      <Link href="/audit" className="quiet-link">
        Go to the audit
      </Link>
    </div>
  );
}
