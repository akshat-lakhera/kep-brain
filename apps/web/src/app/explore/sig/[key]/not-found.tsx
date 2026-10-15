import Link from "next/link";
import type { Route } from "next";
import { serverApi } from "@/lib/api/server";
import { SigLink } from "@/components/explore/links";

export default async function SigNotFound() {
  const meta = await serverApi.meta();
  const sigs = meta.ok ? meta.data.sigs : [];
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-semibold">This SIG is not in the graph</h1>
      <p className="text-fg-secondary">
        {sigs.length ? (
          <>
            Loaded SIGs:{" "}
            <span className="inline-flex flex-wrap gap-x-3">
              {sigs.map((s) => (
                <SigLink key={s} sig={s} />
              ))}
            </span>
            .
          </>
        ) : (
          "The API did not report which SIGs are loaded."
        )}{" "}
        SIG keys are the directory names used in kep.yaml&apos;s owning-sig field.
      </p>
      <Link href={"/explore" as Route} className="quiet-link">
        Back to Explore
      </Link>
    </div>
  );
}
