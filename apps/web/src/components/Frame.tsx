import Link from "next/link";
import type { Route } from "next";
import { serverApi } from "@/lib/api/server";
import { isoUtc, shortSha } from "@/lib/format";
import { REPO_URL } from "@/lib/site";
import { ShortcutsHint } from "./Shortcuts";

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
            {meta.data.sources.tickets_as_of ? (
              <span>
                Issues as of <span className="font-mono">{isoUtc(meta.data.sources.tickets_as_of)}</span>
              </span>
            ) : null}
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
          <Link href="/memory" className="quiet-link">
            Memory
          </Link>
          <Link href={"/about#privacy" as Route} className="quiet-link">
            Privacy
          </Link>
          <ShortcutsHint />
        </span>
        <span className="w-full">
          Code:{" "}
          <a href={REPO_URL} target="_blank" rel="noopener noreferrer" className="quiet-link">
            MIT licence, source on GitHub
          </a>{" "}
          · Data: Kubernetes Enhancement Proposals and issues, © The Kubernetes Authors, Apache-2.0.
        </span>
      </div>
    </footer>
  );
}
