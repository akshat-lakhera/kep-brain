"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useEffect, useId, useRef, useState } from "react";
import { Search } from "lucide-react";
import { clientApi } from "@/lib/api/client";
import type { KepCard } from "@/lib/api/types";
import { numberFromPath } from "@/lib/format";
import { cx } from "@/components/ui";

type Option =
  | { group: "kep"; id: string; href: Route; primary: string; secondary: string; note: string }
  | { group: "sig"; id: string; href: Route; primary: string; secondary: string; note: string }
  | { group: "person"; id: string; href: Route; primary: string; secondary: string; note: string };

type KepState = { kind: "idle" } | { kind: "loading" } | { kind: "error"; code: string } | { kind: "done"; items: KepCard[] };

const GROUP_LABEL: Record<Option["group"], string> = { kep: "KEPs", sig: "SIGs", person: "People" };
const LOGIN = /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})$/;

/**
 * Explore search: KEP numbers and titles from GET /v1/keps?q=, SIG names from the loaded SIGs, and a GitHub
 * login resolved by opening its Person page. Results are one ARIA listbox grouped by type.
 */
export function ExploreSearch({ sigs }: { sigs: { key: string; display_name: string | null }[] }) {
  const router = useRouter();
  const id = useId();
  const listId = `${id}-list`;
  const [q, setQ] = useState("");
  const [keps, setKeps] = useState<KepState>({ kind: "idle" });
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const query = q.trim();

  useEffect(() => {
    if (query.length < 2) return;
    const ctrl = new AbortController();
    const t = setTimeout(async () => {
      setKeps({ kind: "loading" });
      const res = await clientApi.searchKeps(query, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setKeps(res.ok ? { kind: "done", items: res.data.items } : { kind: "error", code: res.error.code });
      setActive(-1);
    }, 200);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [query]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const lower = query.toLowerCase();
  const sigMatches = query.length >= 2 ? sigs.filter((s) => s.key.toLowerCase().includes(lower) || (s.display_name ?? "").toLowerCase().includes(lower)) : [];
  const loginCandidate = query.startsWith("@") ? query.slice(1) : query;
  const options: Option[] = [
    ...(keps.kind === "done" ? keps.items : []).map((k): Option => {
      const n = k.number ?? numberFromPath(k.key);
      return {
        group: "kep",
        id: k.key,
        href: (n !== null ? `/explore/kep/${n}` : "/explore") as Route,
        primary: n !== null ? `KEP-${n}` : k.key,
        secondary: k.title,
        note: [k.owning_sig ?? "", k.status ?? ""].filter(Boolean).join(" · "),
      };
    }),
    ...sigMatches.map(
      (s): Option => ({
        group: "sig",
        id: s.key,
        href: `/explore/sig/${encodeURIComponent(s.key)}` as Route,
        primary: s.key,
        secondary: s.display_name ?? "",
        note: "SIG page",
      }),
    ),
    ...(query.length >= 2 && LOGIN.test(loginCandidate) && !/^\d+$/.test(loginCandidate)
      ? [
          {
            group: "person" as const,
            id: `login:${loginCandidate}`,
            href: `/explore/person/${encodeURIComponent(loginCandidate)}` as Route,
            primary: `@${loginCandidate}`,
            secondary: "Open the Person page for this GitHub login",
            note: "404 if the login is not in the graph",
          },
        ]
      : []),
  ];

  function go(o: Option) {
    setOpen(false);
    router.push(o.href);
  }

  const showList = open && query.length >= 2;
  let lastGroup: Option["group"] | null = null;

  return (
    <div ref={boxRef} className="relative">
      <label htmlFor={`${id}-input`} className="text-sm text-fg-secondary">
        Search KEP numbers, titles, GitHub logins or SIG names
      </label>
      <div className="relative mt-1">
        <Search size={16} strokeWidth={1.5} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-muted" />
        <input
          id={`${id}-input`}
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${id}-opt-${active}` : undefined}
          autoComplete="off"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            if (e.target.value.trim().length < 2) setKeps({ kind: "idle" });
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Home" && options.length) {
              e.preventDefault();
              setActive(0);
            } else if (e.key === "End" && options.length) {
              e.preventDefault();
              setActive(options.length - 1);
            } else if (e.key === "Enter") {
              const pick = active >= 0 ? options[active] : options[0];
              if (pick) {
                e.preventDefault();
                go(pick);
              } else if (/^\d+$/.test(query)) {
                e.preventDefault();
                router.push(`/explore/kep/${query}` as Route);
              }
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          className="h-10 w-full rounded-sm border border-border-input bg-surface pl-9 pr-3 text-base placeholder:text-fg-muted"
        />
      </div>
      {showList ? (
        <div className="absolute left-0 right-0 z-40 mt-1 rounded-md border border-border bg-surface">
          {keps.kind === "loading" ? (
            <p className="px-3 py-2 text-sm text-fg-secondary" role="status">
              Searching KEPs
            </p>
          ) : keps.kind === "error" ? (
            <p className="px-3 py-2 text-sm text-danger" role="alert">
              KEP search failed (<span className="font-mono">{keps.code}</span>); SIG and login matches still work.
            </p>
          ) : null}
          {keps.kind === "done" && options.length === 0 ? (
            <p className="px-3 py-2 text-sm text-fg-secondary" role="status">
              No match in the loaded SIGs for &ldquo;{query}&rdquo;. Loaded SIGs:{" "}
              <span className="font-mono">{sigs.map((s) => s.key).join(", ") || "none reported"}</span>.
            </p>
          ) : null}
          <ul id={listId} role="listbox" aria-label="Search results" className="max-h-96 overflow-y-auto">
            {options.map((o, i) => {
              const header = o.group !== lastGroup;
              lastGroup = o.group;
              return (
                <li key={o.id} className="contents">
                  {header ? (
                    <div role="presentation" className="border-t border-border bg-surface-subtle px-3 py-1 text-xs text-fg-muted first:border-t-0">
                      {GROUP_LABEL[o.group]}
                    </div>
                  ) : null}
                  <div
                    id={`${id}-opt-${i}`}
                    role="option"
                    aria-selected={i === active}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      go(o);
                    }}
                    onMouseEnter={() => setActive(i)}
                    className={cx("cursor-pointer px-3 py-1.5", i === active && "bg-accent-subtle")}
                  >
                    <span className="font-mono text-sm text-accent">{o.primary}</span> <span className="text-sm">{o.secondary}</span>
                    {o.note ? <span className="block font-mono text-xs text-fg-muted">{o.note}</span> : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
