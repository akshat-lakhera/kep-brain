import "server-only";
import { connection } from "next/server";
import { request, type ApiResult } from "./core";
import { paths } from "./endpoints";
import type {
  AgentsBoard,
  DecisionOut,
  EvalQuestion,
  EvalRun,
  FindingsResponse,
  ItemList,
  KepDetail,
  Meta,
  StatusChangeOut,
} from "./types";

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
  kep: (num: number | string, path?: string) => get<KepDetail>(paths.kep(num, path)),
  kepHistory: (num: number | string, path?: string) => get<ItemList<StatusChangeOut>>(paths.kepHistory(num, path)),
  kepDecisions: (num: number | string, path?: string) => get<ItemList<DecisionOut>>(paths.kepDecisions(num, path)),
  findings: (p: Parameters<typeof paths.findings>[0]) => get<FindingsResponse>(paths.findings(p)),
  evalLatest: () => get<EvalRun>(paths.evalLatest()),
  evalQuestions: () => get<{ questions: EvalQuestion[] }>(paths.evalQuestions()),
  agentsBoard: () => get<AgentsBoard>(paths.agentsBoard()),
};
