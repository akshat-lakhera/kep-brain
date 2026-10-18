"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { cx } from "./ui";

export interface TabDef {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

const REVEAL_MS = 1600;

/** Scrolls to an element inside a just-shown panel, focuses it and marks it briefly so the eye finds it. */
function revealTarget(target: HTMLElement) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!target.hasAttribute("tabindex") && !target.matches("a[href], button, input, select, textarea")) target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
  target.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  target.setAttribute("data-revealed", "");
  window.setTimeout(() => target.removeAttribute("data-revealed"), REVEAL_MS);
}

/**
 * WAI-ARIA tabs with roving focus (Left/Right/Home/End). An in-page link (`#id`) anywhere on the page that points into
 * a hidden panel selects that panel's tab first, then scrolls to the target.
 */
export function Tabs({ tabs, initial, label }: { tabs: TabDef[]; initial?: string; label: string }) {
  const base = useId();
  const [active, setActive] = useState(initial ?? tabs[0]?.id);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  // Callers pass a fresh array each render; key the listener on the ids themselves.
  const ids = tabs.map((t) => t.id).join(" ");

  useEffect(() => {
    const tabIds = ids.split(" ");
    function onClick(e: MouseEvent) {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const link = (e.target as Element | null)?.closest?.("a[href^='#']");
      const href = link?.getAttribute("href");
      if (!href || href.length < 2) return;
      let id: string;
      try {
        id = decodeURIComponent(href.slice(1));
      } catch {
        return;
      }
      const target = document.getElementById(id);
      if (!target) return;
      const owner = tabIds.find((t) => document.getElementById(`${base}-panel-${t}`)?.contains(target));
      if (owner === undefined) return;
      e.preventDefault();
      // Show the panel synchronously so the target has a layout box to scroll to.
      flushSync(() => setActive(owner));
      revealTarget(target);
    }
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [base, ids]);

  // A panel is a tab stop only when nothing inside it is (WAI-ARIA APG): a panel that holds links or buttons would
  // otherwise add a redundant stop, and a focusable box around every link inside it. Content streams and changes, so
  // this is checked after every render; the attribute is set here rather than as a prop so React leaves it alone.
  const panelsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    for (const panel of panelsRef.current?.querySelectorAll<HTMLElement>(":scope > [role=tabpanel]") ?? []) {
      const focusable = panel.querySelector("a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex='-1'])");
      if (focusable) panel.removeAttribute("tabindex");
      else panel.setAttribute("tabindex", "0");
    }
  });

  function onKey(e: React.KeyboardEvent, i: number) {
    let next = -1;
    if (e.key === "ArrowRight") next = (i + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (i - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next >= 0) {
      e.preventDefault();
      setActive(tabs[next].id);
      refs.current[next]?.focus();
    }
  }

  return (
    <div>
      <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-border">
        {tabs.map((t, i) => {
          const selected = t.id === active;
          return (
            <button
              key={t.id}
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`${base}-tab-${t.id}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(t.id)}
              onKeyDown={(e) => onKey(e, i)}
              className={cx(
                "-mb-px h-9 whitespace-nowrap border-b-2 px-3 text-base",
                selected ? "border-accent font-medium text-fg" : "border-transparent text-fg-secondary hover:text-fg",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div ref={panelsRef}>
        {tabs.map((t) => (
          <div
            key={t.id}
            role="tabpanel"
            id={`${base}-panel-${t.id}`}
            aria-labelledby={`${base}-tab-${t.id}`}
            hidden={t.id !== active}
            // Server and no-JS markup: a tab stop; the effect above drops it when the panel holds a focusable element.
            tabIndex={0}
            className="pt-4"
          >
            {t.content}
          </div>
        ))}
      </div>
    </div>
  );
}
