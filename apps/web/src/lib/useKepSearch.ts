"use client";

import { useEffect, useState } from "react";
import { clientApi } from "@/lib/api/client";
import type { KepCard } from "@/lib/api/types";

export type KepSearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; code: string }
  | { kind: "done"; items: KepCard[] };

const IDLE: KepSearchState = { kind: "idle" };

/** Debounced GET /v1/keps?q= for a query of at least `minLength` characters; a newer query aborts the older request. */
export function useKepSearch(query: string, minLength = 1): KepSearchState {
  const [state, setState] = useState<KepSearchState>(IDLE);
  useEffect(() => {
    if (query.length < minLength) return;
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setState({ kind: "loading" });
      const res = await clientApi.searchKeps(query, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setState(res.ok ? { kind: "done", items: res.data.items } : { kind: "error", code: res.error.code });
    }, 200);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [query, minLength]);
  // A query that is too short reads as idle at once, without waiting for the effect.
  return query.length < minLength ? IDLE : state;
}
