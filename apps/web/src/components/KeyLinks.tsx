"use client";

import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useEffect } from "react";
import { isTyping } from "@/lib/shortcuts";

export interface KeyLink {
  key: string;
  /** An in-app route (pushed) or an absolute URL (opened in a new tab). */
  href: Route | string;
}

/** Page-level single-letter shortcuts that follow a link; renders nothing. Ignored while typing or in a dialog. */
export function KeyLinks({ links }: { links: KeyLink[] }) {
  const router = useRouter();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (isTyping(e.target) || document.querySelector("dialog[open]")) return;
      if (document.documentElement.hasAttribute("data-chord")) return;
      const link = links.find((l) => l.key === e.key);
      if (!link) return;
      e.preventDefault();
      if (/^https?:\/\//.test(link.href)) window.open(link.href, "_blank", "noopener,noreferrer");
      else router.push(link.href as Route);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [links, router]);
  return null;
}
