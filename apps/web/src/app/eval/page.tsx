import type { Metadata } from "next";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import type { EvalRun } from "@/lib/api/types";
import { pct, readArms, readByKind, readNotRun } from "@/lib/eval";
import { isoUtc, shortSha } from "@/lib/format";
import { KeyValues, RowsTable, asRows, isRecord } from "@/components/DataView";
import { ArmsTable, ByKindTable } from "@/components/EvalArms";
import { Card, EmptyState, ErrorState, Facts, PageHeader, SkeletonBlock } from "@/components/ui";

export const metadata: Metadata = {
  title: "Eval",
  description: "The question set KEP Brain is scored against and the latest recorded run.",
};

export default function EvalPage() {
  return (
    <>
      <PageHeader title="Evaluation" lead="The latest recorded run of the question set, as served by the API." />
      <Suspense fallback={<SkeletonBlock lines={8} label="Loading the latest evaluation run" />}>
        <EvalBody />
      </Suspense>
    </>
  );
}

const SECTIONS: { key: keyof EvalRun; title: string }[] = [
  { key: "audit_precision", title: "Audit precision" },
  { key: "memory", title: "Memory effect" },
  { key: "latency_by_stage", title: "Latency by stage" },
  { key: "load_test", title: "Load test" },
  { key: "baseline", title: "Baseline" },
];

async function EvalBody() {
  const res = await serverApi.evalLatest();
  if (!res.ok) {
    if (res.error.status === 404 || res.error.code === "not_found") {
      return (
        <EmptyState title="No evaluation run recorded">
          <span className="font-mono">/v1/eval/latest</span> returned 404: no <span className="font-mono">evals/runs/*/summary.json</span>{" "}
          exists for this deployment. A run is produced by the eval runner over <span className="font-mono">evals/questions.yaml</span>;
          until then there are no numbers to show.
        </EmptyState>
      );
    }
    return <ErrorState error={res.error} what="Evaluation" />;
  }
  const run = res.data;
  const when = run.created_at ?? run.started_at;
  const facts = [
    run.run_id || run.run ? { label: "Run", value: <span className="font-mono">{run.run_id ?? run.run}</span> } : null,
    when ? { label: "Run at", value: <span className="font-mono">{isoUtc(when)}</span> } : null,
    run.commit ? { label: "Commit", value: <span className="font-mono">{shortSha(run.commit)}</span> } : null,
    typeof run.questions === "number" ? { label: "Questions", value: <span className="tabular">{run.questions}</span> } : null,
    typeof run.reps === "number" ? { label: "Repetitions", value: <span className="tabular">{run.reps}</span> } : null,
    run.model ? { label: "Answering model", value: <span className="font-mono">{run.model}</span> } : null,
    run.judge_model ? { label: "Scoring model", value: <span className="font-mono">{run.judge_model}</span> } : null,
  ].filter((x): x is { label: string; value: React.JSX.Element } => x !== null);

  const arms = readArms(run);
  const notRun = readNotRun(run);
  const armOrder = arms.map((a) => a.arm);
  const byKind = readByKind(run, armOrder);
  const perQuestion = asRows(run.per_question);
  const diff = isRecord(run.paired_difference) ? run.paired_difference : null;
  const diffValue = diff && typeof diff.diff === "number" ? diff.diff : null;
  const diffCi = diff && Array.isArray(diff.ci) && diff.ci.length === 2 ? (diff.ci as [number, number]) : null;
  const spansZero = diffCi !== null && diffCi[0] <= 0 && diffCi[1] >= 0;

  return (
    <div className="space-y-6">
      {facts.length ? (
        <Card title="Run">
          <Facts items={facts} />
          {typeof run.noise_floor === "string" && run.noise_floor ? <p className="mt-3 text-sm text-fg-secondary">{run.noise_floor}</p> : null}
        </Card>
      ) : null}
      <Card title="Accuracy by arm">
        {arms.length || notRun.length ? (
          <>
            <ArmsTable arms={arms} notRun={notRun} />
            {diffValue !== null ? (
              <p className="mt-3 text-sm">
                Paired difference H minus {typeof diff?.baseline === "string" ? <span className="font-mono">{diff.baseline}</span> : "baseline"}:{" "}
                <span className="tabular">{diffValue > 0 ? "+" : ""}{(diffValue * 100).toFixed(1)} points</span>
                {diffCi ? (
                  <>
                    {" "}
                    (95% interval {pct(diffCi[0])} to {pct(diffCi[1])}){spansZero ? ": no measurable difference" : ""}
                  </>
                ) : null}
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-fg-secondary">The run records no per-arm results.</p>
        )}
      </Card>
      <Card title="Accuracy by question type">
        {byKind.length ? (
          <ByKindTable rows={byKind} armOrder={armOrder} />
        ) : isRecord(run.by_kind) && Object.keys(run.by_kind).length ? (
          <RowsTable
            rows={Object.entries(run.by_kind).map(([kind, v]) => ({ kind, ...(isRecord(v) ? v : { value: v }) }))}
            caption="Results by question type"
          />
        ) : (
          <p className="text-fg-secondary">The run has no per-type results.</p>
        )}
      </Card>
      {SECTIONS.map(({ key, title }) => {
        const v = run[key];
        if (!isRecord(v)) return null;
        return (
          <Card key={String(key)} title={title}>
            <KeyValues obj={v} />
          </Card>
        );
      })}
      <Card title={`Per question (${perQuestion.length})`}>
        {perQuestion.length ? (
          <RowsTable rows={perQuestion} caption="Result for each question; rows where a baseline beat the product come first" />
        ) : (
          <p className="text-fg-secondary">The run has no per-question results.</p>
        )}
      </Card>
    </div>
  );
}
