"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

const DURATION_MS = 2500;

interface ToastContextValue {
  /** Shows one short confirmation at the bottom of the screen; a new one replaces the current one. */
  toast: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/** Mounted once in the root layout. Renders the single live region every toast is announced through. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<{ id: number; message: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const counter = useRef(0);

  const toast = useCallback((message: string) => {
    if (timer.current) clearTimeout(timer.current);
    counter.current += 1;
    setCurrent({ id: counter.current, message });
    timer.current = setTimeout(() => {
      timer.current = null;
      setCurrent(null);
    }, DURATION_MS);
  }, []);

  // Clear the timer when the provider unmounts.
  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center px-4"
      >
        {current ? (
          <div
            key={current.id}
            className="fade-in rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-fg shadow-md"
          >
            {current.message}
          </div>
        ) : null}
      </div>
    </ToastContext.Provider>
  );
}

const noop: ToastContextValue = { toast: () => {} };

export function useToast(): ToastContextValue {
  return useContext(ToastContext) ?? noop;
}
