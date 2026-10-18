import { NextResponse, type NextRequest } from "next/server";

/**
 * Real HTTP 404s for KEP, SIG and person pages that name nothing in the graph.
 *
 * The pages are partially prerendered: their static shell (top bar, footer) streams before the page reads the API,
 * and once streaming starts the status is fixed at 200, so a `notFound()` in the page can only render the not-found
 * UI with a noindex tag. This check runs before rendering and asks the API whether the record exists; when it does not,
 * the request is rewritten (the address bar keeps the URL) to a path no route matches, which renders the site's
 * not-found page with a real 404 status.
 *
 * Only document requests are checked (client-side navigations already render the not-found UI); any failure of the
 * check itself (API down, slow, unexpected answer) lets the request through unchanged, so the page shows its own state.
 */

const CHECK_TIMEOUT_MS = 2500;

const NUMBER = /^\d+$/;
const SIG_KEY = /^[a-z0-9][a-z0-9-]{0,80}$/;
const LOGIN = /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})$/;

function apiInternalUrl(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

/** The API path that says whether the page's record exists, null when the segment can never match, undefined to skip. */
function lookupFor(pathname: string, search: URLSearchParams): string | null | undefined {
  const m = /^\/explore\/(kep|sig|person)\/([^/]+)\/?$/.exec(pathname);
  if (!m) return undefined;
  let seg: string;
  try {
    seg = decodeURIComponent(m[2]);
  } catch {
    return null;
  }
  switch (m[1]) {
    case "kep": {
      if (!NUMBER.test(seg)) return null;
      const path = search.get("path");
      return `/v1/keps/${seg}${path ? `?path=${encodeURIComponent(path)}` : ""}`;
    }
    case "sig":
      return SIG_KEY.test(seg) ? `/v1/sigs/${encodeURIComponent(seg)}` : null;
    default:
      return LOGIN.test(seg) ? `/v1/people/${encodeURIComponent(seg)}` : null;
  }
}

/** A path no route matches: Next.js answers it with the root not-found page and status 404. */
const UNMATCHED = "/_not-in-graph";

function notFoundResponse(request: NextRequest): NextResponse {
  // A rewrite's own status is overwritten by the render, so the 404 comes from the unmatched route instead.
  return NextResponse.rewrite(new URL(UNMATCHED, request.url));
}

export async function proxy(request: NextRequest): Promise<NextResponse | undefined> {
  if (request.method !== "GET" && request.method !== "HEAD") return undefined;
  const lookup = lookupFor(request.nextUrl.pathname, request.nextUrl.searchParams);
  if (lookup === undefined) return undefined;
  if (lookup === null) return notFoundResponse(request);
  try {
    const res = await fetch(`${apiInternalUrl()}${lookup}`, {
      method: "GET",
      headers: { accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
    if (res.status !== 404) {
      void res.body?.cancel();
      return undefined;
    }
    // A 404 from an API that does not serve this route at all names no record in its details; the page explains
    // that case itself. A missing record's 404 names what was looked up.
    const body = (await res.json().catch(() => null)) as { error?: { details?: Record<string, unknown> } } | null;
    const details = body?.error?.details;
    if (details && Object.keys(details).length > 0) return notFoundResponse(request);
  } catch {
    // The page renders its own error state.
  }
  return undefined;
}

export const config = {
  matcher: [
    {
      source: "/explore/:kind(kep|sig|person)/:id",
      // Document requests only: RSC payloads for client-side navigations and prefetches keep their normal handling.
      missing: [
        { type: "header", key: "rsc" },
        { type: "header", key: "next-router-prefetch" },
      ],
    },
  ],
};
