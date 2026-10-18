import "server-only";
import { connection } from "next/server";
import { request, type ApiResult } from "./core";
import { paths } from "./endpoints";
import type {
  ChangesResponse,
  DecisionOut,
  EvalRun,
  FindingsResponse,
  ItemList,
  KepDetail,
  KepList,
  Meta,
  StatusChangeOut,
  SyncStatus,
  ToolResult,
  ToolSpec,
} from "./types";
import type { SigCard } from "./types-explore";

/** Base URL of the API as seen from the Next.js server (never sent to the browser). */
export function apiInternalUrl(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

async function get<T>(path: string): Promise<ApiResult<T>> {
  // Read at request time: the graph changes independently of the web build.
  await connection();
  return request<T>(`${apiInternalUrl()}${path}`, { cache: "no-store", headers: { accept: "application/json" } });
}

export const serverApi = {
  meta: () => get<Meta>(paths.meta()),
  keps: (p: Parameters<typeof paths.keps>[0]) => get<KepList>(paths.keps(p)),
  kep: (num: number | string, path?: string) => get<KepDetail>(paths.kep(num, path)),
  kepHistory: (num: number | string, path?: string) => get<ItemList<StatusChangeOut>>(paths.kepHistory(num, path)),
  kepDecisions: (num: number | string, path?: string) => get<ItemList<DecisionOut>>(paths.kepDecisions(num, path)),
  findings: (p: Parameters<typeof paths.findings>[0]) => get<FindingsResponse>(paths.findings(p)),
  evalLatest: () => get<EvalRun>(paths.evalLatest()),
  changes: (p: { since?: string; sig?: string } = {}) => get<ChangesResponse>(paths.changes(p)),
  sigs: () => get<ItemList<SigCard>>(paths.sigs()),
  syncStatus: () => get<SyncStatus>(paths.syncStatus()),
  tools: () => get<ItemList<ToolSpec>>(paths.tools()),
  runTool: async (name: string, params: Record<string, unknown>): Promise<ApiResult<ToolResult>> => {
    await connection();
    return request<ToolResult>(`${apiInternalUrl()}${paths.tool(name)}`, {
      method: "POST",
      cache: "no-store",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(params),
      timeoutMs: 30_000,
    });
  },
};
