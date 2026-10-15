import { Dash } from "@/components/ui";

const ORDER = ["provisional", "implementable", "implemented", "deferred", "withdrawn", "rejected", "replaced"];

/** KEP counts per status as compact single-hue bars, longest scale = the largest count. One series, so no legend. */
export function StatusBars({ counts, caption }: { counts: Record<string, number>; caption: string }) {
  const entries = Object.entries(counts).filter(([, v]) => v > 0);
  if (entries.length === 0) return <Dash />;
  entries.sort(([a], [b]) => {
    const ia = ORDER.indexOf(a);
    const ib = ORDER.indexOf(b);
    return (ia === -1 ? ORDER.length : ia) - (ib === -1 ? ORDER.length : ib) || a.localeCompare(b);
  });
  const max = Math.max(...entries.map(([, v]) => v));
  const total = entries.reduce((s, [, v]) => s + v, 0);
  return (
    <figure>
      <figcaption className="mb-2 text-xs text-fg-muted">{caption}</figcaption>
      <dl className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1.5">
        {entries.map(([status, v]) => (
          <div key={status} className="contents">
            <dt className="font-mono text-sm">{status}</dt>
            <dd className="m-0">
              <div className="h-3 w-full rounded-[2px] bg-surface-subtle">
                <div
                  className="h-3 rounded-[2px] bg-accent"
                  style={{ width: `${Math.max(1, (v / max) * 100)}%` }}
                  role="img"
                  aria-label={`${status}: ${v} of ${total}`}
                />
              </div>
            </dd>
            <dd className="m-0 tabular text-right text-sm">{v.toLocaleString("en-US")}</dd>
          </div>
        ))}
      </dl>
    </figure>
  );
}
