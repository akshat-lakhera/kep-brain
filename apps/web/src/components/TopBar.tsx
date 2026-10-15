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
  { href: "/explore" as Route, label: "Explore" },
  { href: "/audit", label: "Audit" },
  { href: "/memory", label: "Memory" },
  { href: "/about", label: "About" },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({ pathname, onClick, mobile }: { pathname: string; onClick?: () => void; mobile?: boolean }) {
  return NAV.map((item) => {
    const active = isActive(pathname, item.href);
    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={onClick}
        aria-current={active ? "page" : undefined}
        className={cx(
          "inline-flex items-center text-base",
          mobile
            ? cx("h-9 rounded-sm border-l-2 px-3", active ? "border-accent bg-accent-subtle font-semibold text-fg" : "border-transparent text-fg-secondary")
            : cx(
                "-mb-px h-12 border-b-2 px-3",
                active ? "border-accent font-semibold text-fg" : "border-transparent text-fg-secondary hover:border-border-strong hover:text-fg",
              ),
        )}
      >
        {item.label}
      </Link>
    );
  });
}

function CurrentNavLinks({ onClick, mobile }: { onClick?: () => void; mobile?: boolean }) {
  return <NavLinks pathname={usePathname()} onClick={onClick} mobile={mobile} />;
}

function Nav({ onClick, mobile }: { onClick?: () => void; mobile?: boolean }) {
  return (
    <Suspense fallback={<NavLinks pathname="" onClick={onClick} mobile={mobile} />}>
      <CurrentNavLinks onClick={onClick} mobile={mobile} />
    </Suspense>
  );
}

export function TopBar({ dataChip }: { dataChip: ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex h-12 max-w-[1280px] items-center gap-3 px-4 md:px-6">
        <Link href="/" className="mr-2 shrink-0 text-md font-semibold text-fg">
          KEP Brain
        </Link>
        <nav aria-label="Main" className="hidden h-12 items-stretch md:flex">
          <Nav />
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-2">
          <KepSearch />
          {dataChip}
          <ThemeToggle />
          <button
            type="button"
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-border-input md:hidden"
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
        <nav id="mobile-nav" aria-label="Main" className="flex flex-col gap-1 border-t border-border px-4 py-2 md:hidden">
          <Nav onClick={() => setOpen(false)} mobile />
        </nav>
      ) : null}
    </header>
  );
}
