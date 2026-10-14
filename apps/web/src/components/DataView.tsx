import type { ReactNode } from "react";
import { humanize } from "@/lib/format";
import { Dash, ExtLink, TableWrap, cx, tableClass, tdClass, thClass } from "./ui";

/** Render one JSON value compactly: numbers to at most one decimal, URLs as links, objects as JSON. */
export function Value({ v }: { v: unknown }): ReactNode {
  if (v === null || v === undefined || v === "") return <Dash />;
  if (typeof v === "number") return <span className="tabular">{Number.isInteger(v) ? v.toLocaleString("en-US") : v.toFixed(1)}</span>;
  if (typeof v === "boolean") return <span className="font-mono">{v ? "true" : "false"}</span>;
  if (typeof v === "string") {
    if (/^https:\/\//.test(v)) return <ExtLink href={v}>{v.replace(/^https:\/\/(www\.)?/, "").slice(0, 60)}</ExtLink>;
    return <span className={cx(/^[\w.:/#@-]+$/.test(v) && "font-mono")}>{v}</span>;
  }
  if (Array.isArray(v) && v.every((x) => typeof x === "string" || typeof x === "number")) {
    return <span className="font-mono">{v.join(", ")}</span>;
  }
  return <pre className="max-w-[48ch] overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs">{JSON.stringify(v, null, 2)}</pre>;
}

/** A table over rows whose columns are the union of their keys (first `maxCols`). */
export function RowsTable({ rows, caption, maxCols = 8 }: { rows: Record<string, unknown>[]; caption: string; maxCols?: number }) {
  const cols: string[] = [];
  for (const r of rows) {
    for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  }
  const shown = cols.slice(0, maxCols);
  return (
    <TableWrap label={caption}>
      <table className={tableClass}>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {shown.map((c) => (
              <th key={c} className={thClass}>
                {humanize(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {shown.map((c) => (
                <td key={c} className={tdClass}>
                  <Value v={r[c]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

/** Key / value list for a flat or nested object. */
export function KeyValues({ obj }: { obj: Record<string, unknown> }) {
  const entries = Object.entries(obj);
  if (entries.length === 0) return <p className="text-fg-secondary">No values.</p>;
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-sm text-fg-secondary">{humanize(k)}</dt>
          <dd className="break-words">
            <Value v={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function asRows(v: unknown): Record<string, unknown>[] {
  return Array.isArray(v) ? v.filter(isRecord) : [];
}
