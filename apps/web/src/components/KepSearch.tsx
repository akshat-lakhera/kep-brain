"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useEffect, useId, useRef, useState } from "react";
import { Search } from "lucide-react";
import { clientApi } from "@/lib/api/client";
import type { KepCard } from "@/lib/api/types";
import { numberFromPath } from "@/lib/format";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "done"; items: KepCard[] };

function kepNumber(k: KepCard): number | null {
  return k.number ?? numberFromPath(k.key);
}

/** Top-bar KEP search (GET /v1/keps?q=), an ARIA combobox with a listbox of results. */
export function KepSearch() {
  const router = useRouter();
  const id = useId();
  const listId = `${id}-list`;
  const [q, setQ] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) return;
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setState({ kind: "loading" });
      const res = await clientApi.searchKeps(query, ctrl.signal);
      if (ctrl.signal.aborted) return;
      if (res.ok) {
        setState({ kind: "done", items: res.data.items });
        setActive(-1);
      } else {
        setState({ kind: "error", message: res.error.code === "api_unreachable" ? "API unreachable" : "Search failed" });
      }
    }, 200);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [q]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (e.key === "k" && (e.ctrlKey || e.metaKey) && !typing) {
        e.preventDefault();
        boxRef.current?.querySelector("input")?.focus();
      }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const items = q.trim().length >= 2 && state.kind === "done" ? state.items : [];

  function go(k: KepCard) {
    const n = kepNumber(k);
    if (n === null) return;
    setOpen(false);
    setQ("");
    setState({ kind: "idle" });
    router.push(`/explore/kep/${n}` as Route);
  }

  return (
    <div ref={boxRef} className="relative w-40 sm:w-56 md:w-64">
      <label htmlFor={`${id}-input`} className="sr-only">
        Search KEPs by number or title
      </label>
      <Search
        size={16}
        strokeWidth={1.5}
        aria-hidden="true"
        className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-fg-muted"
      />
      <input
        id={`${id}-input`}
        type="search"
        role="combobox"
        aria-expanded={open && q.trim().length >= 2}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
        placeholder="Search KEPs"
        autoComplete="off"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          if (e.target.value.trim().length < 2) setState({ kind: "idle" });
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, items.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter") {
            const pick = active >= 0 ? items[active] : items[0];
            if (pick) {
              e.preventDefault();
              go(pick);
            } else if (/^\d+$/.test(q.trim())) {
              e.preventDefault();
              setOpen(false);
              router.push(`/explore/kep/${q.trim()}` as Route);
            }
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        className="h-8 w-full rounded-sm border border-border-input bg-surface pl-8 pr-2 text-base placeholder:text-fg-muted"
      />
      {open && q.trim().length >= 2 ? (
        <div className="absolute right-0 z-40 mt-1 w-[min(28rem,90vw)] rounded-md border border-border bg-surface">
          {state.kind === "loading" ? (
            <p className="px-3 py-2 text-sm text-fg-secondary" role="status">
              Searching
            </p>
          ) : state.kind === "error" ? (
            <p className="px-3 py-2 text-sm text-danger" role="alert">
              {state.message}
            </p>
          ) : state.kind === "done" && items.length === 0 ? (
            <p className="px-3 py-2 text-sm text-fg-secondary" role="status">
              No KEP in the loaded SIGs matches &ldquo;{q.trim()}&rdquo;.
            </p>
          ) : null}
          <ul id={listId} role="listbox" aria-label="KEP search results" className="max-h-80 overflow-y-auto">
            {items.map((k, i) => {
              const n = kepNumber(k);
              return (
                <li
                  key={k.key}
                  id={`${id}-opt-${i}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    go(k);
                  }}
                  onMouseEnter={() => setActive(i)}
                  className={`cursor-pointer px-3 py-2 ${i === active ? "bg-accent-subtle" : ""}`}
                >
                  <span className="font-mono text-sm text-accent">{n !== null ? `KEP-${n}` : k.key}</span>{" "}
                  <span className="text-sm">{k.title}</span>
                  <span className="block text-xs text-fg-muted">
                    <span className="font-mono">{k.owning_sig ?? ""}</span>
                    {k.status ? ` · ${k.status}` : ""}
                    {k.open_findings > 0 ? ` · ${k.open_findings} open finding${k.open_findings === 1 ? "" : "s"}` : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
