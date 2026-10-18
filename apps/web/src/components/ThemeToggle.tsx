"use client";

import { useSyncExternalStore } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

type Choice = "system" | "light" | "dark";
const KEY = "kep.theme";
const ORDER: Choice[] = ["system", "light", "dark"];
const listeners = new Set<() => void>();

function read(): Choice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function apply(choice: Choice) {
  const dark = choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const onOs = () => {
    if (read() === "system") apply("system");
  };
  mq.addEventListener("change", onOs);
  return () => {
    listeners.delete(cb);
    mq.removeEventListener("change", onOs);
  };
}

/** Three-way theme toggle (system / light / dark); the choice is stored locally. */
export function ThemeToggle() {
  const choice = useSyncExternalStore(subscribe, read, () => "system" as Choice);
  const next = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
  const Icon = choice === "dark" ? Moon : choice === "light" ? Sun : Monitor;
  return (
    <button
      type="button"
      onClick={() => {
        try {
          localStorage.setItem(KEY, next);
        } catch {
          /* storage unavailable: the theme still changes for this page view */
        }
        apply(next);
        listeners.forEach((l) => l());
      }}
      className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border-input text-fg-secondary hover:text-fg"
      aria-label={`Theme: ${choice}. Switch to ${next}.`}
      title={`Theme: ${choice}`}
      data-theme-toggle
    >
      <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
    </button>
  );
}
