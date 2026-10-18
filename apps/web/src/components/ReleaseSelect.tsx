"use client";

import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useId } from "react";

/**
 * "Since release": one native select over the releases the graph knows, in place of a row of chips. Choosing a release
 * navigates to the same href the chips used; the first option returns to the most recent changes.
 */
export function ReleaseSelect({
  current,
  recentHref,
  options,
}: {
  /** The release the page is filtered to, or null for the most recent changes. */
  current: string | null;
  recentHref: Route;
  options: { release: string; href: Route }[];
}) {
  const router = useRouter();
  const id = useId();
  const hrefs = new Map<string, Route>([["", recentHref], ...options.map((o) => [o.release, o.href] as [string, Route])]);
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <label htmlFor={id} className="text-fg-secondary">
        Since release
      </label>
      <select
        id={id}
        value={current ?? ""}
        onChange={(e) => {
          const href = hrefs.get(e.target.value);
          if (href) router.push(href);
        }}
        className="h-9 rounded-sm border border-border-input bg-surface px-2 font-mono text-xs text-fg"
      >
        <option value="">most recent changes</option>
        {options.map((o) => (
          <option key={o.release} value={o.release}>
            {o.release}
          </option>
        ))}
      </select>
    </p>
  );
}
