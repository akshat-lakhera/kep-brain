"use client";

import { useId, useState } from "react";
import { ROWS_MAX, ROWS_PRESETS, type Rows } from "@/lib/rows";
import { cx } from "@/components/ui";

/** The rows-per-page choice: 10, 25, 50, 100, All, or a custom number typed into a small box. */
export function RowsSelect({ value, onChange, className }: { value: Rows; onChange: (rows: Rows) => void; className?: string }) {
  const id = useId();
  const isPreset = value !== "all" && (ROWS_PRESETS as readonly number[]).includes(value);
  const [custom, setCustom] = useState(!isPreset && value !== "all");
  const [draft, setDraft] = useState(value === "all" ? "" : String(value));
  const field = "h-8 rounded-sm border border-border-input bg-surface px-2 text-sm";

  function onSelect(v: string) {
    if (v === "custom") {
      setCustom(true);
      return;
    }
    setCustom(false);
    setDraft(v === "all" ? "" : v);
    onChange(v === "all" ? "all" : Number.parseInt(v, 10));
  }

  function submitCustom() {
    const n = Number.parseInt(draft, 10);
    if (Number.isFinite(n) && n > 0) onChange(Math.min(n, ROWS_MAX));
  }

  const selectValue = custom ? "custom" : value === "all" ? "all" : String(value);

  return (
    <span className={cx("flex flex-wrap items-center gap-2", className)}>
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
    </span>
  );
}
