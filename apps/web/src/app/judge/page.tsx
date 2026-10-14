import type { Metadata, Route } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { serverApi } from "@/lib/api/server";
import type { EvalQuestion } from "@/lib/api/types";
import { Card, Notice, PageHeader, SkeletonBlock } from "@/components/ui";

export const metadata: Metadata = { title: "Judge path" };

/** Judge-path questions from the eval set (docs/design/04-eval-set.md); GET /v1/eval/questions takes precedence. */
const JUDGE_PATH: { id: string; text: string; tools: string; look: string }[] = [
  {
    id: "STA-04",
    text: "What is the status of KEP-583 Coscheduling, and is that metadata current?",
    tools: "find_contradictions → get_kep, kep_relations",
    look: "kep.yaml status against the closed tracking issue, and the successor KEPs that declare they replace it.",
  },
  {
    id: "DEC-07",
    text: "Which KEPs does Gang Scheduling replace, and what became of KEP-5832?",
    tools: "kep_relations → get_kep, find_contradictions",
    look: "The replaces declarations of KEP-4671 and the state of KEP-5832's own records.",
  },
  {
    id: "DEC-01",
    text: "When was KEP-1287 marked implemented, by whom, and in which PR?",
    tools: "trace_decision",
    look: "The commit and pull request that changed the status, and the people on it.",
  },
  {
    id: "MH-07",
    text: "How is soltysh connected to Gang Scheduling (KEP-4671)?",
    tools: "path_between → who_approves",
    look: "The shortest path in the graph between the person and the KEP, with each hop's relationship.",
  },
  {
    id: "ABS-10",
    text: "Which KEP introduced the GangScheduling feature gate?",
    tools: "no evidence expected",
    look: "An abstention: the graph holds no feature gate with that name.",
  },
];

export default function JudgePage() {
  return (
    <>
      <PageHeader
        title="Judge path"
        lead="Five questions from the eval set, in order. Each answer shows the graph it read, every tool call with its parameters, and numbered sources linking to GitHub. Audit and the KEP pages work without the language model."
      />
      <Suspense fallback={<SkeletonBlock lines={6} label="Loading the judge questions" />}>
        <Steps />
      </Suspense>
      <Card title="Then" className="mt-6">
        <ul className="space-y-2">
          <li>
            <Link href="/audit" className="quiet-link">
              Audit
            </Link>
            <span className="text-fg-secondary">: every finding, with both records and their sources.</span>
          </li>
          <li>
            <Link href="/eval" className="quiet-link">
              Eval
            </Link>
            <span className="text-fg-secondary">: the latest evaluation run, per question.</span>
          </li>
          <li>
            <Link href="/about" className="quiet-link">
              About
            </Link>
            <span className="text-fg-secondary">: data sources at their pinned commits.</span>
          </li>
        </ul>
      </Card>
    </>
  );
}

async function Steps() {
  const res = await serverApi.evalQuestions();
  let live: EvalQuestion[] = [];
  if (res.ok) {
    live = res.data.questions
      .filter((q) => typeof q.judge_order === "number")
      .sort((a, b) => (a.judge_order ?? 0) - (b.judge_order ?? 0));
  }
  const steps = live.length
    ? live.map((q) => {
        const known = JUDGE_PATH.find((s) => s.id === q.id);
        return { id: q.id, text: q.text, tools: known?.tools ?? null, look: known?.look ?? null };
      })
    : JUDGE_PATH;

  return (
    <div className="space-y-3">
      {!res.ok ? (
        <Notice>The API did not answer: the questions below are the eval set as written in the repository and cannot be run.</Notice>
      ) : null}
      <ol className="space-y-3">
        {steps.map((s, i) => (
          <li key={s.id} className="flex flex-col gap-3 rounded-md border border-border bg-surface p-4 sm:flex-row sm:items-start">
            <div className="min-w-0 flex-1">
              <p className="font-mono text-xs text-fg-muted">
                {i + 1} · {s.id}
              </p>
              <p className="font-medium">{s.text}</p>
              {s.look ? <p className="mt-1 text-sm text-fg-secondary">Expected evidence: {s.look}</p> : null}
              {s.tools ? (
                <p className="mt-1 text-xs text-fg-muted">
                  Expected tools: <span className="font-mono">{s.tools}</span>
                </p>
              ) : null}
            </div>
            {res.ok ? (
              <Link
                href={`/?q=${encodeURIComponent(s.text)}` as Route}
                className="inline-flex h-8 shrink-0 items-center rounded-sm bg-accent px-3 font-medium text-on-accent hover:bg-accent-hover"
                aria-label={`Ask question ${i + 1}: ${s.text}`}
              >
                Ask
              </Link>
            ) : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
