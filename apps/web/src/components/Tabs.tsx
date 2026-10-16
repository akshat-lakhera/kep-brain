"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { cx } from "./ui";

export interface TabDef {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

/** WAI-ARIA tabs with roving focus (Left/Right/Home/End). */
export function Tabs({ tabs, initial, label }: { tabs: TabDef[]; initial?: string; label: string }) {
  const base = useId();
  const [active, setActive] = useState(initial ?? tabs[0]?.id);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

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
      {tabs.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`${base}-panel-${t.id}`}
          aria-labelledby={`${base}-tab-${t.id}`}
          hidden={t.id !== active}
          tabIndex={0}
          className="pt-4"
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}
