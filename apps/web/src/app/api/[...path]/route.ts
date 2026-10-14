import type { NextRequest } from "next/server";
import { apiInternalUrl } from "@/lib/api/server";

// Same-origin proxy: the browser calls /api/v1/..., this handler forwards to the API.
// Only the public /v1 surface is reachable, and only a fixed set of headers is passed through.

const FORWARD_REQUEST_HEADERS = ["accept", "content-type", "x-kep-memory-id", "x-request-id", "last-event-id"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "x-request-id", "retry-after", "cache-control"];
const SEGMENT = /^[A-Za-z0-9._~:%-]+$/;

function errorResponse(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message, request_id: null, details: null } }, { status });
}

async function forward(req: NextRequest, ctx: RouteContext<"/api/[...path]">): Promise<Response> {
  const { path } = await ctx.params;
  // Forward the raw (still percent-encoded) path so keys containing "/" or ":" survive as one segment.
  const raw = req.nextUrl.pathname.replace(/^\/api\//, "").split("/");
  if (path[0] !== "v1" || raw.length < 2 || raw[0] !== "v1" || !raw.every((s) => SEGMENT.test(s) && s !== ".." && s !== ".")) {
    return errorResponse(404, "not_found", "Unknown API path.");
  }
  const target = `${apiInternalUrl()}/${raw.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "manual",
      signal: req.signal,
    });
  } catch {
    return errorResponse(502, "api_unreachable", "The KEP Brain API could not be reached.");
  }

  const out = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  // Streamed bodies (SSE) pass through unbuffered.
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
