import type { Route } from "next";
import type { GraphNode } from "./api/types";
import { numberFromPath } from "./format";

/** Every in-app href is built here, so a route change is one edit. */
export const routes = {
  kep: (number: number | string) => `/explore/kep/${number}` as Route,
  kepPath: (number: number | string, path: string) => `/explore/kep/${number}?path=${encodeURIComponent(path)}` as Route,
  person: (login: string) => `/explore/person/${encodeURIComponent(login)}` as Route,
  sig: (key: string) => `/explore/sig/${encodeURIComponent(key)}` as Route,
  /** A finding in the audit, landing on the findings table or on the finding's own row. */
  finding: (key: string, anchor: "findings" | "row" = "findings") =>
    `/audit?finding=${encodeURIComponent(key)}#${anchor === "row" ? `f-${encodeURIComponent(key)}` : "findings"}` as Route,
  auditKind: (kind: string) => `/audit?kind=${encodeURIComponent(kind)}#findings` as Route,
  auditSig: (sig: string) => `/audit?sig=${encodeURIComponent(sig)}#findings` as Route,
};

/** The page for a graph node, when its label has one. */
export function pageHref(node: GraphNode): Route | null {
  if (node.label === "KEP") {
    const n = numberFromPath(node.key);
    return n !== null ? routes.kep(n) : null;
  }
  if (node.label === "Person") return routes.person(node.key);
  if (node.label === "SIG") return routes.sig(node.key);
  if (node.label === "Finding") return routes.finding(node.key);
  return null;
}
