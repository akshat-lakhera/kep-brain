"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A count that ticks up from zero the first time it scrolls into view.
 *
 * The server, a page without JavaScript and a reader who prefers reduced motion all get the final value, and so does
 * a count that is already on screen when the page hydrates: resetting a number the reader can already see to zero
 * would flash. Only a count still off screen is set back to zero (where nobody sees it) and ticks up on arrival.
 */
export function CountUp({ value, duration = 700, className }: { value: number; duration?: number; className?: string }) {
  // The frame value belongs to one `value`; a new value shows as is until its own animation (if any) starts.
  const [frame, setFrame] = useState<{ of: number; n: number } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const shown = frame && frame.of === value ? frame.n : value;

  useEffect(() => {
    const el = ref.current;
    if (!el || value <= 0 || typeof IntersectionObserver === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    let first = true;
    const tick = () => {
      let start = 0;
      const step = (t: number) => {
        if (!start) start = t;
        const k = Math.min(1, (t - start) / duration);
        setFrame({ of: value, n: Math.round(value * (1 - Math.pow(1 - k, 3))) });
        if (k < 1) raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    };
    const io = new IntersectionObserver(
      ([entry]) => {
        if (first) {
          first = false;
          // Already visible when the page hydrates: keep the final value, no animation.
          if (entry.isIntersecting) io.disconnect();
          else setFrame({ of: value, n: 0 });
          return;
        }
        if (entry.isIntersecting) {
          io.disconnect();
          tick();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [value, duration]);

  return (
    <span ref={ref} className={className ?? "tabular"}>
      {shown.toLocaleString("en-US")}
    </span>
  );
}
