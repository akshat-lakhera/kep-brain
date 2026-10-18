import { cx } from "./ui";

/** The product mark: three linked nodes on a rounded tile, the same drawing as src/app/icon.svg. */
export function Mark({ className, decorative = false }: { className?: string; decorative?: boolean }) {
  return (
    <svg
      viewBox="0 0 100 100"
      className={cx("shrink-0", className)}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : "KEP Brain"}
      aria-hidden={decorative ? "true" : undefined}
    >
      <rect width="100" height="100" rx="22" className="fill-surface stroke-border" strokeWidth="1" />
      <g className="stroke-accent" strokeOpacity="0.8" strokeWidth="5.5" strokeLinecap="round">
        <line x1="30" y1="30" x2="72" y2="50" />
        <line x1="72" y1="50" x2="30" y2="72" />
        <line x1="30" y1="30" x2="30" y2="72" />
      </g>
      <g className="fill-accent">
        <circle cx="30" cy="30" r="10" />
        <circle cx="72" cy="50" r="13" />
        <circle cx="30" cy="72" r="10" />
      </g>
    </svg>
  );
}
