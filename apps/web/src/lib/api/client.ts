import { request, type ApiFailure, type ApiResult } from "./core";
import { paths } from "./endpoints";
import { getMemoryId } from "../memory";
import { readSse } from "./sse";
import type {
  AgentsBoard,
  ApiErrorBody,
  DecisionOut,
  AskEvent,
  AskResponse,
  FindingDetail,
  GraphOut,
  ItemList,
  KepList,
  MemoryMe,
  ToolResult,
  ToolSpec,
} from "./types";

/** Browser calls go through the same-origin proxy at /api/* (no CORS, no third-party requests). */
const PROXY = "/api";

function headers(withMemory: boolean, json = false): Record<string, string> {
  const h: Record<string, string> = { accept: "application/json" };
  if (json) h["content-type"] = "application/json";
  if (withMemory) {
    const id = getMemoryId();
    if (id) h["x-kep-memory-id"] = id;
  }
  return h;
}

function get<T>(path: string, opts: { memory?: boolean; signal?: AbortSignal } = {}): Promise<ApiResult<T>> {
  return request<T>(`${PROXY}${path}`, {
    headers: headers(Boolean(opts.memory)),
    signal: opts.signal,
    cache: "no-store",
  });
}

function askBody(question: string): string {
  const memoryId = getMemoryId();
  return JSON.stringify(memoryId ? { question, memory_id: memoryId } : { question });
}

const ASK_EVENTS = new Set<string>(["status", "tool_call", "path", "citation", "token", "memory", "done", "error"]);

function plainFailure(code: string, message: string, requestId: string | null = null, status = 0): ApiFailure {
  return { status, code, message, requestId, details: null };
}

/**
 * Outcome of one streamed ask. `fallback` is true when the stream itself failed (transport, no SSE body)
 * rather than the API answering with an error event, so the caller may retry over POST /v1/ask.
 */
export type StreamOutcome = { ok: true } | { ok: false; error: ApiFailure; fallback: boolean };

async function failureOf(res: Response): Promise<ApiFailure> {
  const requestId = res.headers.get("x-request-id");
  let body: ApiErrorBody | null = null;
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  if (body && typeof body === "object" && body.error && typeof body.error.code === "string") {
    return {
      status: res.status,
      code: body.error.code,
      message: body.error.message,
      requestId: body.error.request_id ?? requestId,
      details: body.error.details ?? null,
    };
  }
  return plainFailure("http_error", `The API answered with HTTP ${res.status}.`, requestId, res.status);
}

export const clientApi = {
  searchKeps: (q: string, signal?: AbortSignal) => get<KepList>(paths.keps({ q, limit: 8 }), { signal }),
  /** GET /v1/graph/neighborhood: one hop around a node, for opening it in the evidence chain. */
  neighborhood: (key: string, signal?: AbortSignal) =>
    get<GraphOut>(`/v1/graph/neighborhood?key=${encodeURIComponent(key)}&depth=1&limit=60`, { signal }),
  ask: (question: string, signal?: AbortSignal): Promise<ApiResult<AskResponse>> =>
    request<AskResponse>(`${PROXY}${paths.ask()}`, {
      method: "POST",
      headers: headers(true, true),
      body: askBody(question),
      signal,
      timeoutMs: 150_000,
    }),
  /** POST /v1/ask/stream: every event is handed to `onEvent` as it arrives; resolves when the stream ends. */
  askStream: async (question: string, onEvent: (e: AskEvent) => void, signal: AbortSignal): Promise<StreamOutcome> => {
    let res: Response;
    try {
      res = await fetch(`${PROXY}${paths.askStream()}`, {
        method: "POST",
        headers: { ...headers(true, true), accept: "text/event-stream" },
        body: askBody(question),
        signal,
        cache: "no-store",
      });
    } catch {
      if (signal.aborted) return { ok: false, error: plainFailure("aborted", "The request was cancelled."), fallback: false };
      return { ok: false, error: plainFailure("api_unreachable", "The KEP Brain API could not be reached."), fallback: true };
    }
    if (!res.ok) {
      const error = await failureOf(res);
      // A missing or unsupported stream route is a reason to fall back; a refused question is not.
      return { ok: false, error, fallback: res.status === 404 || res.status === 405 || res.status === 501 };
    }
    const type = res.headers.get("content-type") ?? "";
    if (!res.body || !type.includes("text/event-stream")) {
      return {
        ok: false,
        error: plainFailure("bad_response", "The API did not answer with an event stream.", res.headers.get("x-request-id"), res.status),
        fallback: true,
      };
    }
    let finished = false;
    let errored: ApiFailure | null = null;
    try {
      for await (const msg of readSse(res.body)) {
        if (!ASK_EVENTS.has(msg.event)) continue;
        let data: unknown;
        try {
          data = JSON.parse(msg.data);
        } catch {
          continue;
        }
        const ev = { event: msg.event, data } as AskEvent;
        if (ev.event === "error") {
          errored = plainFailure(ev.data.code, ev.data.message, ev.data.request_id ?? null);
        }
        onEvent(ev);
        if (ev.event === "done" || ev.event === "error") finished = true;
      }
    } catch {
      if (signal.aborted) return { ok: false, error: plainFailure("aborted", "The request was cancelled."), fallback: false };
      return { ok: false, error: plainFailure("bad_response", "The event stream was interrupted."), fallback: true };
    }
    if (errored) return { ok: false, error: errored, fallback: false };
    if (!finished) {
      return { ok: false, error: plainFailure("bad_response", "The event stream ended before the answer was done."), fallback: true };
    }
    return { ok: true };
  },
  finding: (key: string, signal?: AbortSignal) => get<FindingDetail>(paths.finding(key), { signal }),
  /** Decisions on one KEP; `path` disambiguates a reused number. */
  kepDecisions: (num: number, path?: string, signal?: AbortSignal) =>
    get<ItemList<DecisionOut>>(paths.kepDecisions(num, path), { signal }),
  draftIssue: (findingKey: string, signal?: AbortSignal): Promise<ApiResult<ToolResult>> =>
    clientApi.runTool("draft_stale_doc_issue", { finding_key: findingKey }, signal),
  tools: (signal?: AbortSignal) => get<ItemList<ToolSpec>>(paths.tools(), { signal }),
  /** POST /v1/tools/{name} with the parameters as the body. Tool queries may wait on the graph, so 60 s. */
  runTool: (name: string, params: Record<string, unknown>, signal?: AbortSignal): Promise<ApiResult<ToolResult>> =>
    request<ToolResult>(`${PROXY}${paths.tool(name)}`, {
      method: "POST",
      headers: headers(false, true),
      body: JSON.stringify(params),
      signal,
      timeoutMs: 60_000,
    }),
  memoryMe: () => get<MemoryMe>(paths.memoryMe(), { memory: true }),
  forgetMemory: () =>
    request<{ deleted: boolean }>(`${PROXY}${paths.memoryMe()}`, { method: "DELETE", headers: headers(true) }),
  agentsBoard: () => get<AgentsBoard>(paths.agentsBoard()),
};
