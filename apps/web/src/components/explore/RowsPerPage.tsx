"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { ROWS_DEFAULT, type Rows } from "@/lib/rows";
import { RowsSelect } from "@/components/RowsSelect";

/**
 * Rows-per-page control for a server-rendered table: writes `?rows=` (and resets `?page=`) into the URL, so the
 * page re-renders with that slice and the choice survives reload and sharing.
 */
export function RowsPerPage({ value, param = "rows", pageParam = "page" }: { value: Rows; param?: string; pageParam?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function apply(next: Rows) {
    const sp = new URLSearchParams(params.toString());
    if (next === ROWS_DEFAULT) sp.delete(param);
    else sp.set(param, String(next));
    sp.delete(pageParam);
    const qs = sp.toString();
    router.replace(`${pathname}${qs ? `?${qs}` : ""}` as Route, { scroll: false });
  }

  return <RowsSelect value={value} onChange={apply} className="text-sm text-fg-secondary" />;
}
