import type { EvalArmNotRun } from "@/lib/api/types";
import { pct, type ArmRow, type KindRow } from "@/lib/eval";
import { Dash, TableWrap, cx, tableClass, tdClass, thClass } from "./ui";

/** The product arm (04 §8.2) is drawn in the accent colour; every other arm in grey. Labels carry the value. */
const PRODUCT_ARM = "H";

function Bar({ value, product, label }: { value: number | null; product: boolean; label: string }) {
  if (value === null) return <Dash />;
  const width = Math.max(0, Math.min(100, value * 100));
  return (
    <div className="flex items-center gap-2" aria-hidden="true">
      <div className="h-3 w-40 max-w-full rounded-sm bg-surface-subtle" title={label}>
        <div className={cx("h-3 rounded-sm", product ? "bg-accent" : "bg-border-strong")} style={{ width: `${width}%` }} />
      </div>
      <span className="tabular text-sm">{pct(value)}</span>
    </div>
  );
}

/** Accuracy per arm: one table whose rows carry an inline bar, so the table is the accessible twin of the chart. */
export function ArmsTable({ arms, notRun }: { arms: ArmRow[]; notRun: EvalArmNotRun[] }) {
  return (
    <TableWrap label="Accuracy by arm">
      <table className={tableClass}>
        <caption className="mb-2 text-left text-sm text-fg-secondary">
          Accuracy over the scored questions per arm, with the Wilson 95% interval and n where the run records them. Arm {PRODUCT_ARM} is the product.
        </caption>
        <thead>
          <tr>
            <th className={thClass}>Arm</th>
            <th className={thClass}>Accuracy</th>
            <th className={thClass}>95% interval</th>
            <th className={cx(thClass, "text-right")}>Correct</th>
            <th className={cx(thClass, "text-right")}>n</th>
            <th className={cx(thClass, "text-right")}>Abstained</th>
            <th className={cx(thClass, "text-right")}>Errored</th>
          </tr>
        </thead>
        <tbody>
          {arms.map((a) => (
            <tr key={a.arm}>
              <td className={tdClass}>
                <span className="font-mono font-medium">{a.arm}</span>
                {a.name ? <span className="ml-2 text-fg-secondary">{a.name}</span> : null}
                {a.arm === PRODUCT_ARM ? <span className="ml-2 text-xs text-fg-muted">(product)</span> : null}
              </td>
              <td className={tdClass}>
                <span className="sr-only">{pct(a.accuracy)}</span>
                <Bar value={a.accuracy} product={a.arm === PRODUCT_ARM} label={`${a.arm}: ${pct(a.accuracy)}`} />
              </td>
              <td className={cx(tdClass, "tabular")}>{a.ci ? `${pct(a.ci[0])} to ${pct(a.ci[1])}` : <Dash />}</td>
              <td className={cx(tdClass, "tabular text-right")}>{a.correct ?? <Dash />}</td>
              <td className={cx(tdClass, "tabular text-right")}>{a.n ?? <Dash />}</td>
              <td className={cx(tdClass, "tabular text-right")}>{a.abstained ?? <Dash />}</td>
              <td className={cx(tdClass, "tabular text-right")}>{a.errored ?? <Dash />}</td>
            </tr>
          ))}
          {notRun.map((a) => (
            <tr key={`not-run-${a.arm}`}>
              <td className={tdClass}>
                <span className="font-mono font-medium">{a.arm}</span>
              </td>
              <td className={cx(tdClass, "text-fg-secondary")} colSpan={6}>
                Not run{a.reason ? `: ${a.reason}` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

/** Accuracy per question type and arm; indicative only (04 §7: about ±18 points per type). */
export function ByKindTable({ rows, armOrder }: { rows: KindRow[]; armOrder: string[] }) {
  const arms = armOrder.filter((arm) => rows.some((r) => arm in r.arms));
  return (
    <TableWrap label="Accuracy by question type">
      <table className={tableClass}>
        <caption className="mb-2 text-left text-sm text-fg-secondary">
          Per-type numbers come from about ten questions each and are indicative only.
        </caption>
        <thead>
          <tr>
            <th className={thClass}>Type</th>
            <th className={cx(thClass, "text-right")}>n</th>
            {arms.map((arm) => (
              <th key={arm} className={thClass}>
                <span className="font-mono">{arm}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.kind}>
              <td className={cx(tdClass, "font-mono")}>{r.kind}</td>
              <td className={cx(tdClass, "tabular text-right")}>{r.n ?? r.arms[arms[0]]?.n ?? <Dash />}</td>
              {arms.map((arm) => {
                const a = r.arms[arm];
                return (
                  <td key={arm} className={tdClass}>
                    {a ? (
                      <>
                        <span className="sr-only">{pct(a.accuracy)}</span>
                        <Bar value={a.accuracy} product={arm === PRODUCT_ARM} label={`${r.kind} ${arm}: ${pct(a.accuracy)}`} />
                      </>
                    ) : (
                      <Dash />
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
