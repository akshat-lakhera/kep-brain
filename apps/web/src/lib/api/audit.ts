import "server-only";
import { connection } from "next/server";
import { qs, request, type ApiResult } from "./core";
import { apiInternalUrl } from "./server";
import type { ChangesResponse, SigSummary, SyncStatus } from "./types";

async function get<T>(path: string): Promise<ApiResult<T>> {
  await connection();
  return request<T>(`${apiInternalUrl()}${path}`, { cache: "no-store", headers: { accept: "application/json" } });
}

/** Routes that newer API builds serve; a 404 means this deployment does not have them yet. */
export const auditApi = {
  changes: (p: { since?: string; sig?: string }) => get<ChangesResponse>(`/v1/changes${qs(p)}`),
  syncStatus: () => get<SyncStatus>("/v1/sync/status"),
  sigs: () => get<{ items: SigSummary[] } | SigSummary[]>("/v1/sigs"),
};
