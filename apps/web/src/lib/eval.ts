import type { EvalArm, EvalArmNotRun, EvalRun } from "./api/types";
import { isRecord } from "@/components/DataView";

/** One arm as the Eval page shows it; every number is null when the summary does not carry it. */
export interface ArmRow {
  arm: string;
  name: string | null;
  accuracy: number | null;
  n: number | null;
  correct: number | null;
  ci: [number, number] | null;
  abstained: number | null;
  errored: number | null;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Accuracies may be written as 0..1 or as percentages; both become a fraction. */
function fraction(v: unknown): number | null {
  const x = num(v);
  if (x === null) return null;
  return x > 1 ? x / 100 : x;
}

function interval(v: unknown): [number, number] | null {
  if (Array.isArray(v) && v.length === 2) {
    const lo = fraction(v[0]);
    const hi = fraction(v[1]);
    return lo !== null && hi !== null ? [lo, hi] : null;
  }
  if (isRecord(v)) {
    const lo = fraction(v.lo ?? v.low ?? v.lower);
    const hi = fraction(v.hi ?? v.high ?? v.upper);
    return lo !== null && hi !== null ? [lo, hi] : null;
  }
  return null;
}

function armRow(arm: string, v: unknown): ArmRow {
  const o: Partial<EvalArm> = isRecord(v) ? (v as Partial<EvalArm>) : {};
  const n = num(o.n);
  const correct = num(o.correct);
  const accuracy = fraction(o.accuracy) ?? (n && correct !== null ? correct / n : null);
  return {
    arm,
    name: typeof o.name === "string" ? o.name : null,
    accuracy,
    n,
    correct,
    ci: interval(o.ci),
    abstained: num(o.abstained),
    errored: num(o.errored),
  };
}

export function readArms(run: EvalRun): ArmRow[] {
  const arms = run.arms;
  if (Array.isArray(arms)) {
    return arms.map((a) => (typeof a === "string" ? armRow(a, null) : armRow(String(a.arm), a)));
  }
  if (isRecord(arms)) {
    return Object.entries(arms).map(([arm, v]) => (typeof v === "number" ? armRow(arm, { accuracy: v }) : armRow(arm, v)));
  }
  return [];
}

export function readNotRun(run: EvalRun): EvalArmNotRun[] {
  const v = run.arms_not_run;
  if (Array.isArray(v)) return v.filter((x) => isRecord(x) && typeof x.arm === "string").map((x) => ({ arm: x.arm, reason: String(x.reason ?? "") }));
  if (isRecord(v)) return Object.entries(v).map(([arm, reason]) => ({ arm, reason: String(reason) }));
  return [];
}

export interface KindRow {
  kind: string;
  n: number | null;
  arms: Record<string, ArmRow>;
}

/** `by_kind[kind][arm]` → accuracy per arm; scalar values under an arm letter are read as accuracies. */
export function readByKind(run: EvalRun, armOrder: string[]): KindRow[] {
  if (!isRecord(run.by_kind)) return [];
  const rows: KindRow[] = [];
  for (const [kind, v] of Object.entries(run.by_kind)) {
    if (!isRecord(v)) continue;
    const arms: Record<string, ArmRow> = {};
    for (const arm of armOrder) {
      if (arm in v) arms[arm] = typeof v[arm] === "number" ? armRow(arm, { accuracy: v[arm] }) : armRow(arm, v[arm]);
    }
    if (Object.keys(arms).length === 0) continue;
    rows.push({ kind, n: num(v.n), arms });
  }
  return rows;
}

export function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}
