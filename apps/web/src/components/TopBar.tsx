"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { Menu, X } from "lucide-react";
import { KepSearch } from "./KepSearch";
import { ThemeToggle } from "./ThemeToggle";
import { cx } from "./ui";

const NAV: { href: Route; label: string }[] = [
  { href: "/", label: "Ask" },
  { href: "/audit", label: "Audit" },
  { href: "/memory", label: "Memory" },
  { href: "/eval", label: "Eval" },
  { href: "/judge", label: "Judge" },
  { href: "/about", label: "About" },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({ pathname, onClick }: { pathname: string; onClick?: () => void }) {
  return NAV.map((item) => {
    const active = isActive(pathname, item.href);
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onClick}
        aria-current={active ? "page" : undefined}
        className={cx(
          "inline-flex h-9 items-center rounded-sm px-3 text-base",
          active ? "bg-accent-subtle font-medium text-accent" : "text-fg-secondary hover:bg-surface-subtle hover:text-fg",
        )}
      >
        {item.label}
      </Link>
    );
  });
}

function CurrentNavLinks({ onClick }: { onClick?: () => void }) {
  return <NavLinks pathname={usePathname()} onClick={onClick} />;
}

function Nav({ onClick }: { onClick?: () => void }) {
  return (
    <Suspense fallback={<NavLinks pathname="" onClick={onClick} />}>
      <CurrentNavLinks onClick={onClick} />
    </Suspense>
  );
}

export function TopBar({ dataChip }: { dataChip: ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-[1280px] items-center gap-3 px-4 py-2 md:px-6">
        <Link href="/" className="shrink-0 text-md font-semibold text-fg">
          KEP Brain
        </Link>
        <nav aria-label="Main" className="hidden items-center gap-1 lg:flex">
          <Nav />
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          <KepSearch />
          {dataChip}
          <ThemeToggle />
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-border-input lg:hidden"
            aria-expanded={open}
            aria-controls="mobile-nav"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X size={18} strokeWidth={1.5} aria-hidden="true" /> : <Menu size={18} strokeWidth={1.5} aria-hidden="true" />}
          </button>
        </div>
      </div>
      {open ? (
        <nav id="mobile-nav" aria-label="Main" className="flex flex-col gap-1 border-t border-border px-4 py-2 lg:hidden">
          <Nav onClick={() => setOpen(false)} />
        </nav>
      ) : null}
    </header>
  );
}
