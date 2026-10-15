import { qs, request, type ApiFailure, type ApiResult } from "./core";
import type { ItemList } from "./types";
import type { ChangesOut, PersonOut, SigCard, SigDetail } from "./types-explore";

const n = (v: string) => encodeURIComponent(v);

export const explorePaths = {
  person: (login: string) => `/v1/people/${n(login)}`,
  sigs: () => "/v1/sigs",
  sig: (key: string) => `/v1/sigs/${n(key)}`,
  changes: (p: { since?: string; sig?: string }) => `/v1/changes${qs(p)}`,
};

/** Path templates as the OpenAPI document lists them, for feature detection. */
export const exploreTemplates = {
  person: "/v1/people/{login}",
  sig: "/v1/sigs/{key}",
};

/**
 * The API answers every unknown URL with the same not_found envelope as a missing record, so a route is
 * feature-detected through the OpenAPI document: served when a path template with the same shape is listed.
 * Unknown (the document could not be read) counts as served, so a 404 then falls through to the real 404 page.
 */
export function routeServed(openapi: ApiResult<{ paths?: Record<string, unknown> }>, template: string): boolean {
  if (!openapi.ok || !openapi.data.paths) return true;
  const shape = (p: string) => p.replace(/\{[^}]*\}/g, "{}").replace(/\/+$/, "");
  const want = shape(template);
  return Object.keys(openapi.data.paths).some((p) => shape(p) === want);
}

export function isNotFound(error: ApiFailure): boolean {
  return error.status === 404 || error.code === "not_found";
}

/**
 * Explore calls against a base: the internal API URL on the server, the same-origin proxy ("/api") in the browser.
 * Server callers `await connection()` first so the graph is read at request time.
 */
export function exploreApi(base: string, signal?: AbortSignal) {
  const root = base.replace(/\/+$/, "");
  const get = <T,>(path: string) =>
    request<T>(`${root}${path}`, { cache: "no-store", headers: { accept: "application/json" }, signal });
  return {
    person: (login: string) => get<PersonOut>(explorePaths.person(login)),
    sigs: () => get<ItemList<SigCard>>(explorePaths.sigs()),
    sig: (key: string) => get<SigDetail>(explorePaths.sig(key)),
    changes: (p: { since?: string; sig?: string } = {}) => get<ChangesOut>(explorePaths.changes(p)),
    openapi: () => get<{ paths?: Record<string, unknown> }>("/openapi.json"),
  };
}

export type ExploreApi = ReturnType<typeof exploreApi>;
export type { ApiResult };
