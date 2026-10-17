"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { GO_KEYS, SHORTCUTS_EVENT, SHORTCUT_GROUPS, isTyping } from "@/lib/shortcuts";

const CHORD_MS = 1500;

/**
 * Where `/` goes: the question box on Ask, else the page's own search, else the top-bar KEP search. Only a rendered
 * field counts: after a client-side navigation the previous page can still be in the DOM, hidden.
 */
function searchTarget(): HTMLElement | null {
  const candidates = ["#ask-input", '[data-search="page"]', '[data-search="top"]'];
  for (const sel of candidates) {
    for (const el of document.querySelectorAll<HTMLElement>(sel)) {
      if (el.getClientRects().length > 0) return el;
    }
  }
  return null;
}

/** One `<kbd>` per key. */
export function Keys({ keys }: { keys: string[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {keys.map((k, i) => (
        <span key={k} className="inline-flex items-center gap-1">
          {i > 0 ? <span className="text-xs text-fg-muted">or</span> : null}
          <kbd>{k}</kbd>
        </span>
      ))}
    </span>
  );
}

/**
 * Global keyboard shortcuts and the `?` help dialog. Single letters are ignored while typing in a field and while
 * another dialog is open; `g` starts a chord that goes to a page.
 */
export function Shortcuts() {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const chord = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    function toggle() {
      if (!dialog) return;
      if (dialog.open) dialog.close();
      else dialog.showModal();
    }
    function endChord() {
      if (chord.current) clearTimeout(chord.current);
      chord.current = null;
      document.documentElement.removeAttribute("data-chord");
    }
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.key === "Escape") return;
      if (isTyping(e.target)) return;
      const otherModal = document.querySelector("dialog[open]");
      if (otherModal && otherModal !== dialog) return;
      if (e.key === "?") {
        e.preventDefault();
        toggle();
        return;
      }
      if (dialog?.open) return;
      if (chord.current) {
        // The second key of a chord never reaches page shortcuts, whether or not it names a page.
        e.preventDefault();
        const to = GO_KEYS.find((g) => g.key === e.key.toLowerCase());
        endChord();
        if (to) router.push(to.href);
        return;
      }
      if (e.key === "g") {
        chord.current = setTimeout(endChord, CHORD_MS);
        document.documentElement.setAttribute("data-chord", "g");
        return;
      }
      if (e.key === "/") {
        const target = searchTarget();
        if (target) {
          e.preventDefault();
          target.focus();
          if (target instanceof HTMLInputElement) target.select();
        }
        return;
      }
      if (e.key === "t") {
        const toggleButton = document.querySelector<HTMLButtonElement>("[data-theme-toggle]");
        if (toggleButton) {
          e.preventDefault();
          toggleButton.click();
        }
      }
    }
    function onOpenRequest() {
      if (dialog && !dialog.open) dialog.showModal();
    }
    function onBackdrop(e: MouseEvent) {
      if (e.target === dialog) dialog?.close();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener(SHORTCUTS_EVENT, onOpenRequest);
    dialog?.addEventListener("click", onBackdrop);
    return () => {
      endChord();
      document.removeEventListener("keydown", onKey);
      document.removeEventListener(SHORTCUTS_EVENT, onOpenRequest);
      dialog?.removeEventListener("click", onBackdrop);
    };
  }, [router]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="shortcuts-title"
      className="m-auto w-[min(44rem,92vw)] max-h-[85vh] rounded-md border border-border bg-surface p-0 text-fg shadow-xl backdrop:bg-black/50"
    >
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h2 id="shortcuts-title" className="text-md font-semibold">
          Keyboard shortcuts
        </h2>
        <button
          type="button"
          onClick={() => dialogRef.current?.close()}
          aria-label="Close"
          className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-fg-secondary hover:text-fg"
        >
          <X size={18} strokeWidth={1.5} aria-hidden="true" />
        </button>
      </div>
      <div className="grid gap-x-8 gap-y-5 overflow-y-auto px-5 py-4 md:grid-cols-2">
        {SHORTCUT_GROUPS.map((g) => (
          <section key={g.title} aria-labelledby={`sc-${g.title}`}>
            <h3 id={`sc-${g.title}`} className="eyebrow">
              {g.title}
            </h3>
            {g.where ? <p className="mt-0.5 text-xs text-fg-muted">{g.where}</p> : null}
            <dl className="mt-2 space-y-1.5">
              {g.items.map((it) => (
                <div key={it.action} className="flex flex-row-reverse items-baseline justify-between gap-4 text-sm">
                  <dt className="shrink-0">
                    <Keys keys={it.keys} />
                  </dt>
                  <dd className="text-fg-secondary">{it.action}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      <p className="border-t border-border px-5 py-2 text-xs text-fg-muted">
        Shortcuts pause while you type in a field. Press <kbd>?</kbd> or <kbd>Esc</kbd> to close.
      </p>
    </dialog>
  );
}

/** A small "? shortcuts" button for footers and help lines; opens the dialog. */
export function ShortcutsHint({ className }: { className?: string }) {
  return (
    <button
      type="button"
      className={className ?? "quiet-link inline-flex items-center gap-1"}
      onClick={() => document.dispatchEvent(new Event(SHORTCUTS_EVENT))}
    >
      <kbd>?</kbd> Shortcuts
    </button>
  );
}
