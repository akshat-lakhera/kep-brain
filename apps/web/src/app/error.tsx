"use client";

import Link from "next/link";
import { useEffect } from "react";

/** Route error boundary: shown in place of the page when rendering it throws. */
export default function PageError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div role="alert" className="mx-auto max-w-[60ch] space-y-4 py-10">
      <h1 className="text-xl font-semibold">This page could not be shown</h1>
      <p className="text-fg-secondary">
        Something failed while building the page. The graph and the API may be fine; try again, and if it keeps failing
        the digest below helps find the cause in the server logs.
      </p>
      {error.digest ? (
        <p className="font-mono text-xs text-fg-muted">digest {error.digest}</p>
      ) : error.message ? (
        <p className="break-words font-mono text-xs text-fg-muted">{error.message.slice(0, 300)}</p>
      ) : null}
      <div className="flex flex-wrap gap-3 text-sm">
        <button type="button" onClick={reset} className="h-8 rounded-sm bg-accent px-3 font-medium text-on-accent hover:bg-accent-hover">
          Try again
        </button>
        <Link href="/ask" className="quiet-link self-center">
          Back to Ask
        </Link>
      </div>
    </div>
  );
}
