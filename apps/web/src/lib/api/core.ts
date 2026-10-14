import type { ApiErrorBody } from "./types";

export interface ApiFailure {
  status: number;
  code: string;
  message: string;
  requestId: string | null;
  details: Record<string, unknown> | null;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiFailure };

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const err = (value as { error: unknown }).error;
  return typeof err === "object" && err !== null && "code" in err;
}

function failure(status: number, code: string, message: string, requestId: string | null = null): ApiFailure {
  return { status, code, message, requestId, details: null };
}

/** Perform one request and normalise every outcome (network, HTTP, JSON) into an ApiResult. */
export async function request<T>(
  url: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<ApiResult<T>> {
  const { timeoutMs = 15_000, ...rest } = init;
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = rest.signal ? AbortSignal.any([rest.signal, timeout]) : timeout;
  let res: Response;
  try {
    res = await fetch(url, { ...rest, signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError" && rest.signal?.aborted) {
      return { ok: false, error: failure(0, "aborted", "The request was cancelled.") };
    }
    if (err instanceof DOMException && (err.name === "TimeoutError" || err.name === "AbortError")) {
      return { ok: false, error: failure(0, "timeout", "The request took too long.") };
    }
    return { ok: false, error: failure(0, "api_unreachable", "The KEP Brain API could not be reached.") };
  }
  const requestId = res.headers.get("x-request-id");
  let body: unknown = null;
  let text = "";
  try {
    text = await res.text();
  } catch {
    return { ok: false, error: failure(res.status, "bad_response", "The API response was interrupted.", requestId) };
  }
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!res.ok) {
    if (isErrorBody(body)) {
      return {
        ok: false,
        error: {
          status: res.status,
          code: body.error.code,
          message: body.error.message,
          requestId: body.error.request_id ?? requestId,
          details: body.error.details ?? null,
        },
      };
    }
    const code =
      res.status === 404 ? "not_found" : res.status === 502 || res.status === 503 ? "api_unreachable" : "http_error";
    return { ok: false, error: failure(res.status, code, `The API answered with HTTP ${res.status}.`, requestId) };
  }
  if (body === null) {
    return { ok: false, error: failure(res.status, "bad_response", "The API sent an empty or invalid response.", requestId) };
  }
  return { ok: true, data: body as T };
}

export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
