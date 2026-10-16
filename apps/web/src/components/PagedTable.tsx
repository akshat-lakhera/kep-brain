"use client";

import { useState, type ReactNode } from "react";
import { ROWS_DEFAULT, type Rows } from "@/lib/rows";
import { RowsSelect } from "@/components/RowsSelect";
import { TableWrap, tableClass } from "@/components/ui";

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
  const { rows, page, pages, start, end, total, setRows, setPage } = paging;
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
        <RowsSelect value={rows} onChange={setRows} className="ml-2 text-fg-secondary" />
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
