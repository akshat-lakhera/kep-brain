"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { useId, useState } from "react";
import { ROWS_DEFAULT, ROWS_MAX, ROWS_PRESETS } from "@/lib/rows";

/**
 * Rows-per-page control for a server-rendered table: writes `?rows=` (and resets `?page=`) into the URL, so the
 * page re-renders with that slice and the choice survives reload and sharing.
 */
export function RowsPerPage({ value, param = "rows", pageParam = "page" }: { value: number | "all"; param?: string; pageParam?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const id = useId();
  const isPreset = value !== "all" && (ROWS_PRESETS as readonly number[]).includes(value);
  const [custom, setCustom] = useState(!isPreset && value !== "all");
  const [draft, setDraft] = useState(value === "all" ? "" : String(value));

  function apply(next: string) {
    const sp = new URLSearchParams(params.toString());
    if (next === String(ROWS_DEFAULT)) sp.delete(param);
    else sp.set(param, next);
    sp.delete(pageParam);
    const qs = sp.toString();
    router.replace(`${pathname}${qs ? `?${qs}` : ""}` as Route, { scroll: false });
  }

  function onSelect(v: string) {
    if (v === "custom") {
      setCustom(true);
      return;
    }
    setCustom(false);
    setDraft(v === "all" ? "" : v);
    apply(v);
  }

  function submitCustom() {
    const n = Number.parseInt(draft, 10);
    if (Number.isFinite(n) && n > 0) apply(String(Math.min(n, ROWS_MAX)));
  }

  const selectValue = custom ? "custom" : value === "all" ? "all" : String(value);
  const field = "h-8 rounded-sm border border-border-input bg-surface px-2 text-sm";

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-fg-secondary">
      <label htmlFor={`${id}-rows`}>Rows</label>
      <select id={`${id}-rows`} className={field} value={selectValue} onChange={(e) => onSelect(e.target.value)}>
        {ROWS_PRESETS.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
        <option value="all">All</option>
        <option value="custom">Custom…</option>
      </select>
      {custom ? (
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submitCustom();
          }}
        >
          <label htmlFor={`${id}-custom`} className="sr-only">
            Custom number of rows
          </label>
          <input
            id={`${id}-custom`}
            type="number"
            min={1}
            max={ROWS_MAX}
            inputMode="numeric"
            className={`${field} w-24 tabular`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={submitCustom}
            autoFocus
          />
          <button type="submit" className="quiet-link">
            Apply
          </button>
        </form>
      ) : null}
    </div>
  );
}
