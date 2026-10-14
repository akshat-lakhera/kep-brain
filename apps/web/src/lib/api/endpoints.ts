import { qs } from "./core";

const n = (v: number | string) => encodeURIComponent(String(v));

/** Paths of the /v1 API, shared by the server and browser clients. */
export const paths = {
  meta: () => "/v1/meta",
  keps: (p: { q?: string; sig?: string; status?: string; limit?: number }) => `/v1/keps${qs(p)}`,
  kep: (num: number | string, path?: string) => `/v1/keps/${n(num)}${qs({ path })}`,
  kepHistory: (num: number | string, path?: string) => `/v1/keps/${n(num)}/history${qs({ path })}`,
  kepDecisions: (num: number | string, path?: string) => `/v1/keps/${n(num)}/decisions${qs({ path })}`,
  findings: (p: { kind?: string; sig?: string; state?: string }) => `/v1/findings${qs(p)}`,
  finding: (key: string) => `/v1/findings/${n(key)}`,
  tool: (name: string) => `/v1/tools/${n(name)}`,
  ask: () => "/v1/ask",
  askStream: () => "/v1/ask/stream",
  evalLatest: () => "/v1/eval/latest",
  evalQuestions: () => "/v1/eval/questions",
  memoryMe: () => "/v1/memory/me",
  agentsBoard: () => "/v1/agents/board",
};
