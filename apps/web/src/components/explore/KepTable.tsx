"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { KepCard } from "@/lib/api/types";
import { routes } from "@/lib/routes";
import { numberFromPath } from "@/lib/format";
import { Dash, SigLink, StatusChip, TableWrap, cx, tableClass, tdClass, thClass } from "@/components/ui";
import { PagerBar, usePaging } from "@/components/PagedTable";
import { SortHeader } from "@/components/SortHeader";

type Col = "number" | "title" | "status" | "stage" | "latest_milestone" | "owning_sig" | "open_findings";

const COLS: { id: Col; label: string }[] = [
  { id: "number", label: "KEP" },
  { id: "title", label: "Title" },
  { id: "status", label: "Status" },
  { id: "stage", label: "Stage" },
  { id: "latest_milestone", label: "Latest" },
  { id: "owning_sig", label: "SIG" },
  { id: "open_findings", label: "Open findings" },
];

function cell(k: KepCard, c: Col): string | number | null {
  if (c === "number") return k.number ?? numberFromPath(k.key);
  return k[c];
}

function compare(a: KepCard, b: KepCard, c: Col): number {
  const x = cell(a, c);
  const y = cell(b, c);
  if (x === null && y === null) return 0;
  if (x === null) return 1;
  if (y === null) return -1;
  if (typeof x === "number" && typeof y === "number") return x - y;
  return String(x).localeCompare(String(y), "en", { numeric: true, sensitivity: "base" });
}

/** KEP cards as a sortable table (sortable headers are buttons; aria-sort on the active column). */
export function KepTable({
  items,
  caption,
  label,
  hideSig = false,
  extra,
}: {
  items: KepCard[];
  caption?: string;
  label: string;
  hideSig?: boolean;
  /** Extra column rendered after the KEP title, keyed by KEP key (used for the PRR stage). */
  extra?: { label: string; values: Record<string, string> };
}) {
  const [sort, setSort] = useState<{ col: Col; dir: 1 | -1 }>({ col: "number", dir: 1 });
  const sorted = useMemo(() => {
    const out = [...items];
    out.sort((a, b) => compare(a, b, sort.col) * sort.dir);
    return out;
  }, [items, sort]);
  const cols = COLS.filter((c) => !(hideSig && c.id === "owning_sig"));
  const paging = usePaging(sorted.length);

  function toggle(col: Col) {
    setSort((s) => (s.col === col ? { col, dir: s.dir === 1 ? -1 : 1 } : { col, dir: 1 }));
  }

  return (
    <div>
    <PagerBar paging={paging} note={caption} />
    <TableWrap label={label}>
      <table className={tableClass}>
        <caption className="sr-only">{label}</caption>
        <thead>
          <tr>
            {cols.map((c) => {
              const active = sort.col === c.id;
              return (
                <SortHeader
                  key={c.id}
                  active={active}
                  dir={sort.dir}
                  onClick={() => toggle(c.id)}
                  className="p-0"
                  buttonClassName="flex h-9 w-full px-3 text-left font-medium"
                >
                  {c.label}
                </SortHeader>
              );
            })}
            {extra ? <th className={thClass}>{extra.label}</th> : null}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(paging.start, paging.end).map((k) => {
            const num = k.number ?? numberFromPath(k.key);
            return (
              <tr key={k.key}>
                <td className={cx(tdClass, "whitespace-nowrap")}>
                  {num !== null ? (
                    <Link href={routes.kep(num)} className="quiet-link ident">
                      KEP-{num}
                    </Link>
                  ) : (
                    <span className="ident">{k.key}</span>
                  )}
                </td>
                <td className={cx(tdClass, "min-w-56")}>{k.title}</td>
                <td className={tdClass}>
                  <StatusChip status={k.status} />
                </td>
                <td className={cx(tdClass, "font-mono")}>{k.stage ?? <Dash />}</td>
                <td className={cx(tdClass, "font-mono")}>{k.latest_milestone ?? <Dash />}</td>
                {hideSig ? null : <td className={tdClass}>{k.owning_sig ? <SigLink sig={k.owning_sig} /> : <Dash />}</td>}
                <td className={cx(tdClass, "tabular text-right")}>{k.open_findings}</td>
                {extra ? <td className={cx(tdClass, "font-mono")}>{extra.values[k.key] ?? <Dash />}</td> : null}
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableWrap>
    </div>
  );
}
