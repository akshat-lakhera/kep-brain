import Link from "next/link";
import type { Route } from "next";
import { serverApi } from "@/lib/api/server";
import { shortSha } from "@/lib/format";

/** "Data as of" chip: the ingested enhancements commit and the ticket snapshot time, from /v1/meta. */
export async function DataChip() {
  const meta = await serverApi.meta();
  if (!meta.ok) {
    return (
      <span className="inline-flex h-7 items-center rounded-sm border border-danger/40 bg-danger-subtle px-2 text-xs text-danger">
        API unreachable
      </span>
    );
  }
  const sha = meta.data.sources.enhancements_sha;
  const asOf = meta.data.sources.tickets_as_of;
  return (
    <Link
      href={"/audit#sync" as Route}
      className="hidden h-7 items-center gap-1 rounded-sm border border-border bg-surface-subtle px-2 text-xs text-fg-secondary hover:border-border-strong sm:inline-flex"
      title={`kubernetes/enhancements at ${sha ?? "unknown"}${asOf ? `; tickets as of ${asOf}` : ""}`}
    >
      <span className="hidden sm:inline">Data as of</span>
      {asOf ? <span className="font-mono">{asOf.slice(0, 10)}</span> : null}
      {sha ? <span className={asOf ? "hidden font-mono md:inline" : "font-mono"}>{asOf ? "· " : ""}{shortSha(sha)}</span> : null}
    </Link>
  );
}

export async function Footer() {
  const meta = await serverApi.meta();
  return (
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-4 text-xs text-fg-secondary md:px-6">
        {meta.ok ? (
          <>
            {meta.data.falkordb_image ? (
              <span>
                FalkorDB <span className="font-mono">{meta.data.falkordb_image}</span>
              </span>
            ) : null}
            <span>
              Model{" "}
              <span className="font-mono">
                {meta.data.llm.configured ? `${meta.data.llm.provider ?? ""} ${meta.data.llm.model ?? ""}`.trim() : "not configured"}
              </span>
            </span>
            {meta.data.sources.enhancements_sha ? (
              <span>
                kubernetes/enhancements <span className="font-mono">{shortSha(meta.data.sources.enhancements_sha)}</span>
              </span>
            ) : null}
          </>
        ) : (
          <span>API status unknown: the API did not answer.</span>
        )}
        <span className="ml-auto flex gap-4">
          <Link href="/about" className="quiet-link">
            About
          </Link>
          <Link href="/tools" className="quiet-link">
            Tools
          </Link>
          <Link href="/eval" className="quiet-link">
            Eval
          </Link>
        </span>
        <span className="w-full">
          Data: Kubernetes Enhancement Proposals and issues, © The Kubernetes Authors, Apache-2.0.
        </span>
      </div>
    </footer>
  );
}
