import Link from "next/link";
import type { Route } from "next";
import { absoluteUrl } from "@/lib/site";
import { JsonLd } from "./JsonLd";

export interface Crumb {
  label: string;
  /** In-app path. The last crumb is the current page and is not linked. */
  href: Route;
}

/** The path to the current page, small and muted, with a matching BreadcrumbList for crawlers. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  if (items.length === 0) return null;
  const last = items.length - 1;
  return (
    <>
      <nav aria-label="Breadcrumb" className="text-xs text-fg-muted">
        <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
          {items.map((item, i) => (
            <li key={`${item.href}-${i}`} className="flex items-center gap-x-1.5">
              {i > 0 ? (
                <span aria-hidden="true" className="text-border-strong">
                  /
                </span>
              ) : null}
              {i === last ? (
                <span aria-current="page" className="text-fg-secondary">
                  {item.label}
                </span>
              ) : (
                <Link href={item.href} className="hover:text-fg hover:underline">
                  {item.label}
                </Link>
              )}
            </li>
          ))}
        </ol>
      </nav>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: items.map((item, i) => ({
            "@type": "ListItem",
            position: i + 1,
            name: item.label,
            item: absoluteUrl(item.href),
          })),
        }}
      />
    </>
  );
}
