"use client";

import { useId, useState, type ReactNode } from "react";
import { ROWS_DEFAULT, ROWS_MAX, ROWS_PRESETS } from "@/lib/rows";
import { TableWrap, tableClass } from "@/components/ui";

type Rows = number | "all";

/** Page state for a list of `total` items: rows per page (preset, custom or all) and the current page. */
export function usePaging(total: number, defaultRows: Rows = ROWS_DEFAULT) {
  const [rows, setRowsState] = useState<Rows>(defaultRows);
  const [page, setPageState] = useState(1);
  const size = rows === "all" ? Math.max(1, total) : rows;
  const pages = Math.max(1, Math.ceil(total / size));
  const current = Math.min(page, pages);
  const start = (current - 1) * size;
  const end = Math.min(total, start + size);
  return {
    rows,
    page: current,
    pages,
    start,
    end,
    total,
    setRows: (r: Rows) => {
      setRowsState(r);
      setPageState(1);
    },
    setPage: (p: number) => setPageState(Math.min(Math.max(1, p), pages)),
  };
}

export type Paging = ReturnType<typeof usePaging>;

/**
 * Toolbar for a paged table: a note on the left; "Showing a–b of N · Previous · Next" and the rows-per-page choice
 * (10, 25, 50, 100, All or a custom number) on the right.
 */
export function PagerBar({ paging, note }: { paging: Paging; note?: ReactNode }) {
  const id = useId();
  const { rows, page, pages, start, end, total, setRows, setPage } = paging;
  const isPreset = rows !== "all" && (ROWS_PRESETS as readonly number[]).includes(rows);
  const [custom, setCustom] = useState(!isPreset && rows !== "all");
  const [draft, setDraft] = useState(rows === "all" ? "" : String(rows));
  const field = "h-8 rounded-sm border border-border-input bg-surface px-2 text-sm";

  function onSelect(v: string) {
    if (v === "custom") {
      setCustom(true);
      return;
    }
    setCustom(false);
    setRows(v === "all" ? "all" : Number.parseInt(v, 10));
    setDraft(v === "all" ? "" : v);
  }

  function submitCustom() {
    const n = Number.parseInt(draft, 10);
    if (Number.isFinite(n) && n > 0) setRows(Math.min(n, ROWS_MAX));
  }

  const selectValue = custom ? "custom" : rows === "all" ? "all" : String(rows);
  const link = "quiet-link disabled:text-fg-muted disabled:no-underline";

  return (
    <div className="mb-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs text-fg-muted">
      <span>{note}</span>
      <span className="flex flex-wrap items-center gap-2">
        <span className="tabular">
          Showing {total === 0 ? 0 : (start + 1).toLocaleString("en-US")}–{end.toLocaleString("en-US")} of {total.toLocaleString("en-US")}
        </span>
        {pages > 1 ? (
          <>
            <button type="button" className={link} disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <button type="button" className={link} disabled={page >= pages} onClick={() => setPage(page + 1)}>
              Next
            </button>
          </>
        ) : null}
        <label htmlFor={`${id}-rows`} className="ml-2 text-fg-secondary">
          Rows
        </label>
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
    </div>
  );
}

/**
 * A server-rendered table shown one page at a time. The page passes the header row and every body row already
 * rendered; only the visible slice is mounted. The choice is per visit (not in the URL).
 */
export function PagedTable({
  label,
  caption,
  head,
  rows,
  defaultRows = ROWS_DEFAULT,
}: {
  label: string;
  /** Shown as the toolbar note and as the table's accessible caption. */
  caption?: ReactNode;
  /** The `<tr>` of header cells. */
  head: ReactNode;
  /** One rendered `<tr>` per item, each with a key. */
  rows: ReactNode[];
  defaultRows?: Rows;
}) {
  const paging = usePaging(rows.length, defaultRows);
  return (
    <div>
      <PagerBar paging={paging} note={caption} />
      <TableWrap label={label}>
        <table className={tableClass}>
          <caption className="sr-only">{label}</caption>
          <thead>{head}</thead>
          <tbody>{rows.slice(paging.start, paging.end)}</tbody>
        </table>
      </TableWrap>
    </div>
  );
}
