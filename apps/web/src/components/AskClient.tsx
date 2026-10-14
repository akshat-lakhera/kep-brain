"use client";

import Link from "next/link";
import type { Route } from "next";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Ban, Copy, Link2 } from "lucide-react";
import { clientApi } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/core";
import type {
  AskEvent,
  AskResponse,
  Citation,
  EvalQuestion,
  GraphOut,
  SseCitation,
  SseDone,
  SseMemory,
  SseStatus,
  SseToolCall,
} from "@/lib/api/types";
import { ms } from "@/lib/format";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { GraphPanel } from "./GraphPanel";
import { Tabs } from "./Tabs";
import { Chip, EmptyState, ErrorState, ExtLink, cx, tableClass, tdClass, thClass } from "./ui";

const MIN = 3;
const MAX = 1000;
const SLOW_AFTER_MS = 10_000;
// The API's own budget is 90 s of planning plus the waits a rate-limited provider asks for.
const ABORT_AFTER_MS = 150_000;

/** Everything one ask has produced so far, filled event by event (or at once from POST /v1/ask). */
interface Live {
  question: string;
  started: number;
  mode: "stream" | "fallback";
  status: SseStatus | null;
  toolCalls: SseToolCall[];
  graph: GraphOut;
  /** Evidence read by tools, in arrival order (citation events without an index). */
  evidence: SseCitation[];
  /** The numbered citations of the checked answer (citation events with an index, or the /v1/ask list). */
  citations: Citation[];
  answer: string;
  memory: SseMemory | null;
  done: SseDone | null;
  model: string | null;
}

type Phase =
  | { kind: "idle" }
  | { kind: "live"; live: Live }
  | { kind: "done"; live: Live }
  | { kind: "error"; live: Live; error: ApiFailure };

function emptyLive(question: string, mode: Live["mode"]): Live {
  return {
    question,
    started: Date.now(),
    mode,
    status: null,
    toolCalls: [],
    graph: { nodes: [], edges: [] },
    evidence: [],
    citations: [],
    answer: "",
    memory: null,
    done: null,
    model: null,
  };
}

function mergeGraph(a: GraphOut, b: GraphOut): GraphOut {
  const nodes = new Map(a.nodes.map((n) => [n.id, n]));
  for (const n of b.nodes) if (!nodes.has(n.id)) nodes.set(n.id, n);
  const edgeKey = (e: GraphOut["edges"][number]) => `${e.source}\u0000${e.target}\u0000${e.type}`;
  const edges = new Map(a.edges.map((e) => [edgeKey(e), e]));
  for (const e of b.edges) if (!edges.has(edgeKey(e))) edges.set(edgeKey(e), e);
  return { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()) };
}

function apply(live: Live, ev: AskEvent): Live {
  switch (ev.event) {
    case "status":
      return { ...live, status: ev.data };
    case "tool_call":
      return { ...live, toolCalls: [...live.toolCalls.filter((t) => t.step !== ev.data.step), ev.data] };
    case "path":
      return { ...live, graph: mergeGraph(live.graph, ev.data) };
    case "citation": {
      const c = ev.data;
      if (typeof c.index === "number") {
        const citation: Citation = { index: c.index, evidence_id: c.evidence_id, label: c.source_type, key: c.locator, title: c.title, url: c.url };
        return { ...live, citations: [...live.citations.filter((x) => x.index !== c.index), citation].sort((x, y) => x.index - y.index) };
      }
      if (live.evidence.some((x) => x.evidence_id === c.evidence_id)) return live;
      return { ...live, evidence: [...live.evidence, c] };
    }
    case "token":
      return { ...live, answer: live.answer + ev.data.text };
    case "memory":
      return { ...live, memory: ev.data };
    case "done":
      return { ...live, done: ev.data };
    case "error":
      return live;
  }
}

function fromResponse(question: string, started: number, d: AskResponse): Live {
  return {
    question,
    started,
    mode: "fallback",
    status: null,
    toolCalls: d.tool_calls,
    graph: d.graph,
    evidence: [],
    citations: d.citations,
    answer: d.answer_markdown,
    memory: { recalled: d.memory.recalled, remembered: d.memory.remembered, findings_recalled: d.findings_recalled },
    done: {
      request_id: d.request_id,
      nodes_read: d.graph.nodes.length,
      sources: d.citations.length,
      latency_ms: d.latency_ms,
      abstained: d.abstained,
      abstain_reason: d.abstain_reason ?? null,
    },
    model: d.model,
  };
}

const RATE_LIMIT_PHASE = /rate|wait|limit|retry/i;

/** The status line while an answer is in flight: the API's own label, or the honest rate-limit wording. */
function statusText(status: SseStatus | null): string {
  if (!status) return "Sending the question";
  if (RATE_LIMIT_PHASE.test(status.phase)) {
    const wait = typeof status.wait_s === "number" && status.wait_s > 0 ? ` for ${Math.round(status.wait_s)} s` : "";
    return `Waiting for the model (rate limit)${wait}`;
  }
  return status.label || status.phase;
}

export function AskClient({ sigs }: { sigs: string[] | null }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const initialQ = params.get("q") ?? "";
  const [text, setText] = useState(initialQ);
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [now, setNow] = useState(0);
  const [suggestions, setSuggestions] = useState<EvalQuestion[] | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastAsked = useRef<string | null>(null);

  const run = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (q.length < MIN || q.length > MAX) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      lastAsked.current = q;
      const started = Date.now();
      setNow(started);
      setPhase({ kind: "live", live: emptyLive(q, "stream") });
      if (params.get("q") !== q) router.replace(`${pathname}?q=${encodeURIComponent(q)}` as Route, { scroll: false });
      const hardStop = setTimeout(() => ctrl.abort("timeout"), ABORT_AFTER_MS);

      const update = (f: (live: Live) => Live) =>
        setPhase((p) => (p.kind === "live" && abortRef.current === ctrl ? { kind: "live", live: f(p.live) } : p));

      let sawEvent = false;
      const outcome = await clientApi.askStream(
        q,
        (ev) => {
          sawEvent = true;
          update((live) => apply(live, ev));
        },
        ctrl.signal,
      );
      if (abortRef.current !== ctrl) {
        clearTimeout(hardStop);
        return;
      }
      if (outcome.ok) {
        clearTimeout(hardStop);
        setPhase((p) => (p.kind === "live" ? { kind: "done", live: p.live } : p));
        return;
      }
      const timedOut = ctrl.signal.aborted && ctrl.signal.reason === "timeout";
      if (!outcome.fallback || ctrl.signal.aborted) {
        clearTimeout(hardStop);
        const error = timedOut ? { ...outcome.error, code: "timeout", message: "No answer within 150 seconds." } : outcome.error;
        setPhase((p) => ({ kind: "error", live: p.kind === "idle" ? emptyLive(q, "stream") : p.live, error }));
        return;
      }
      // The stream failed before the answer was done: ask again over the plain endpoint.
      setPhase({ kind: "live", live: { ...emptyLive(q, "fallback"), started, status: { phase: "fallback", label: sawEvent ? "Stream interrupted; asking again without streaming" : "Asking without streaming" } } });
      const res = await clientApi.ask(q, ctrl.signal);
      clearTimeout(hardStop);
      if (abortRef.current !== ctrl) return;
      if (res.ok) {
        setPhase({ kind: "done", live: fromResponse(q, started, res.data) });
      } else {
        setPhase({ kind: "error", live: emptyLive(q, "fallback"), error: res.error });
      }
    },
    [params, pathname, router],
  );

  // Run the question from ?q= (deep links from /judge and shared links).
  useEffect(() => {
    const q = params.get("q");
    if (q && q !== lastAsked.current) {
      setText(q);
      void run(q);
    }
  }, [params, run]);

  // Elapsed time on the status line while an answer is in flight.
  useEffect(() => {
    if (phase.kind !== "live") return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [phase.kind]);

  useEffect(() => {
    let live = true;
    clientApi.evalQuestions().then((res) => {
      if (!live) return;
      if (!res.ok) {
        setSuggestions([]);
        return;
      }
      const qs = res.data.questions
        .filter((q) => typeof q.judge_order === "number")
        .sort((a, b) => (a.judge_order ?? 0) - (b.judge_order ?? 0))
        .slice(0, 3);
      setSuggestions(qs);
    });
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      live = false;
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const loading = phase.kind === "live";
  const len = text.trim().length;
  const tooLong = len > MAX;

  function cancel() {
    abortRef.current?.abort();
    abortRef.current = null;
    setPhase((p) =>
      p.kind === "live"
        ? { kind: "error", live: p.live, error: { status: 0, code: "aborted", message: "The request was cancelled.", requestId: null, details: null } }
        : p,
    );
  }

  async function copy(kind: "answer" | "link") {
    if (phase.kind !== "done") return;
    const d = phase.live;
    const sources = d.citations.length
      ? d.citations.map((c) => `[${c.index}] ${c.label} ${c.title ?? c.key} ${c.url ?? ""}`)
      : d.evidence.map((c) => `- ${c.source_type} ${c.title ?? c.locator} ${c.url ?? ""}`);
    const value =
      kind === "link"
        ? `${window.location.origin}/?q=${encodeURIComponent(d.question)}`
        : `${d.answer}\n\nSources:\n${sources.join("\n")}`;
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  const liveStatus = phase.kind === "live" ? statusText(phase.live.status) : "";

  return (
    <div className="space-y-6">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(text);
        }}
        className="rounded-md border border-border bg-surface p-4"
        aria-busy={loading}
      >
        <label htmlFor="ask-input" className="mb-1 block font-medium">
          Ask about Kubernetes Enhancement Proposals
        </label>
        <textarea
          id="ask-input"
          ref={inputRef}
          value={text}
          rows={2}
          maxLength={MAX + 200}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!loading) void run(text);
            } else if (e.key === "Escape" && loading) {
              cancel();
            }
          }}
          aria-describedby="ask-help"
          aria-invalid={tooLong}
          className="block min-h-16 w-full resize-y rounded-sm border border-border-input bg-surface p-2 text-base"
          placeholder="What is the status of KEP-583, and is that metadata current?"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p id="ask-help" className="text-xs text-fg-muted">
            Enter sends, Shift+Enter adds a line, / focuses this box, Escape cancels.
            {len >= 900 ? (
              <span className={cx("ml-2 tabular", tooLong && "text-danger")}>
                {len.toLocaleString("en-US")} / 1,000 characters
              </span>
            ) : null}
          </p>
          <div className="flex gap-2">
            {loading ? (
              <button type="button" onClick={cancel} className="h-8 rounded-sm border border-border-input px-3 text-base">
                Cancel
              </button>
            ) : null}
            <button
              type="submit"
              disabled={loading || len < MIN || tooLong}
              className="h-8 rounded-sm bg-accent px-4 text-base font-medium text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
            >
              Ask
            </button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" aria-label="Suggested questions">
          {suggestions === null ? (
            <span className="text-xs text-fg-muted">Loading suggested questions</span>
          ) : (
            suggestions.map((s) => (
              <button
                key={s.id}
                type="button"
                disabled={loading}
                onClick={() => {
                  setText(s.text);
                  void run(s.text);
                }}
                className="min-h-7 max-w-full rounded-sm border border-border bg-surface-subtle px-2 py-1 text-left text-sm hover:border-border-strong disabled:opacity-50"
              >
                <span className="mr-1 font-mono text-xs text-fg-muted">{s.id}</span>
                {s.text}
              </button>
            ))
          )}
        </div>
      </form>

      <div aria-live="polite" className="sr-only">
        {phase.kind === "live" ? liveStatus : phase.kind === "done" ? "Answer ready" : ""}
      </div>

      {phase.kind === "idle" ? (
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <EmptyState title="No question asked yet">
              <p>
                Answers come from a graph of KEPs, people, SIGs, pull requests, issues and their history. Each answer lists
                the tool calls it made and the sources it cites; the steps appear as they run, and the text appears once
                every claim has been checked against the graph.
              </p>
              <p className="mt-2">
                {sigs ? (
                  <>
                    Loaded SIGs: <span className="font-mono">{sigs.join(", ")}</span>.
                  </>
                ) : (
                  "The API did not report which SIGs are loaded."
                )}{" "}
                No e-mail addresses are stored.
              </p>
            </EmptyState>
          </div>
          <aside aria-label="Evidence" className="lg:col-span-5">
            <EmptyState title="Evidence">The graph read, the tool calls and the sources appear here.</EmptyState>
          </aside>
        </div>
      ) : null}

      {phase.kind === "error" ? (
        <div className="space-y-3">
          <p className="font-medium">{phase.live.question}</p>
          <ErrorState error={phase.error} what="No answer">
            <button
              type="button"
              onClick={() => void run(phase.live.question)}
              className="h-8 rounded-sm border border-border-input bg-surface px-3"
            >
              Retry
            </button>
          </ErrorState>
          {phase.live.toolCalls.length > 0 ? (
            <div className="lg:max-w-[60%]">
              <p className="mb-2 text-sm text-fg-secondary">Steps completed before it stopped</p>
              <Steps live={phase.live} />
            </div>
          ) : null}
        </div>
      ) : null}

      {phase.kind === "live" || phase.kind === "done" ? (
        <AnswerView
          live={phase.live}
          final={phase.kind === "done"}
          statusLine={phase.kind === "live" ? `${liveStatus} · ${phase.live.toolCalls.length} tool call${phase.live.toolCalls.length === 1 ? "" : "s"} · ${ms(Math.max(0, now - phase.live.started))}${now - phase.live.started > SLOW_AFTER_MS ? " · still working" : ""}` : null}
          copied={copied}
          onCopy={copy}
        />
      ) : null}
    </div>
  );
}

function AnswerView({
  live,
  final,
  statusLine,
  copied,
  onCopy,
}: {
  live: Live;
  final: boolean;
  statusLine: string | null;
  copied: string | null;
  onCopy: (k: "answer" | "link") => void;
}) {
  const citedKeys = new Set(live.citations.map((c) => c.key));
  const pathNodeIds = live.graph.nodes.filter((n) => citedKeys.has(n.key)).map((n) => n.id);
  const failedCalls = live.toolCalls.filter((t) => t.error).length;
  const done = live.done;
  const sourceCount = live.citations.length || live.evidence.length;
  const findingsRecalled = live.memory?.findings_recalled ?? [];

  return (
    <div className="grid gap-6 lg:grid-cols-12">
      <article className="min-w-0 lg:col-span-7" aria-label="Answer" aria-busy={!final}>
        <p className="mb-1 text-sm text-fg-secondary" role="status">
          {statusLine ??
            (done ? (
              <>
                {live.toolCalls.length} tool call{live.toolCalls.length === 1 ? "" : "s"} · {done.nodes_read} node{done.nodes_read === 1 ? "" : "s"} read ·{" "}
                {done.sources} source{done.sources === 1 ? "" : "s"} · {ms(done.latency_ms)}
                {live.model ? (
                  <>
                    {" "}
                    · <span className="font-mono">{live.model}</span>
                  </>
                ) : null}
                {live.mode === "fallback" ? " · not streamed" : null}
              </>
            ) : null)}
        </p>
        <h2 className="mb-3 text-md font-semibold">{live.question}</h2>
        {done?.abstained ? (
          <div className="mb-3 rounded-md border border-border bg-surface-subtle p-4">
            <p className="flex items-center gap-2 font-medium">
              <Ban size={16} strokeWidth={1.5} aria-hidden="true" />
              No evidence in the graph for this question
            </p>
            {done.abstain_reason ? (
              <p className="mt-1 text-fg-secondary">
                Reason: <span className="font-mono">{done.abstain_reason}</span>
              </p>
            ) : null}
            <p className="mt-1 text-fg-secondary">The tool calls it tried are listed under Steps. Name a SIG or a KEP number to narrow it.</p>
          </div>
        ) : null}
        {live.answer ? (
          <div className="rounded-md border border-border bg-surface p-4">
            <AnswerMarkdown markdown={live.answer} citations={live.citations} />
          </div>
        ) : !final ? (
          <div className="space-y-2" aria-hidden="true">
            <div className="skeleton h-4 w-11/12" />
            <div className="skeleton h-4 w-10/12" />
            <div className="skeleton h-4 w-8/12" />
          </div>
        ) : null}
        {failedCalls > 0 ? (
          <p className="mt-2 text-sm text-warning">
            {failedCalls} tool call{failedCalls === 1 ? "" : "s"} failed; see Steps.
          </p>
        ) : null}
        {final ? (
          <>
            <div className="mt-3 flex flex-wrap gap-2">
              {findingsRecalled.length > 0 ? (
                <Link href={"/audit" as Route} className="no-underline">
                  <Chip tone="warning">
                    Used {findingsRecalled.length} shared finding{findingsRecalled.length === 1 ? "" : "s"}
                  </Chip>
                </Link>
              ) : null}
              {live.memory && live.memory.recalled.length > 0 ? (
                <Link href="/memory" className="no-underline">
                  <Chip>Recalled from your memory: {live.memory.recalled.length}</Chip>
                </Link>
              ) : null}
              {live.memory && live.memory.remembered.length > 0 ? (
                <Link href="/memory" className="no-underline">
                  <Chip>Remembered: {live.memory.remembered.join(", ")}</Chip>
                </Link>
              ) : null}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={() => onCopy("answer")} className="inline-flex h-7 items-center gap-1 rounded-sm border border-border-input px-2 text-sm">
                <Copy size={14} strokeWidth={1.5} aria-hidden="true" />
                {copied === "answer" ? "Copied" : "Copy answer"}
              </button>
              <button type="button" onClick={() => onCopy("link")} className="inline-flex h-7 items-center gap-1 rounded-sm border border-border-input px-2 text-sm">
                <Link2 size={14} strokeWidth={1.5} aria-hidden="true" />
                {copied === "link" ? "Copied" : "Copy link"}
              </button>
            </div>
            {done ? (
              <p className="mt-2 text-xs text-fg-muted">
                Diagnostic id <span className="font-mono">{done.request_id}</span>
              </p>
            ) : null}
          </>
        ) : null}
      </article>

      <aside aria-label="Evidence" className="min-w-0 lg:col-span-5">
        <Tabs
          label="Evidence"
          tabs={[
            {
              id: "graph",
              label: `Graph (${live.graph.nodes.length})`,
              content: (
                <GraphPanel
                  graph={live.graph}
                  layout={live.graph.nodes.length > 50 ? "fcose" : "dagre"}
                  pathNodeIds={pathNodeIds}
                  label={`Evidence graph with ${live.graph.nodes.length} nodes and ${live.graph.edges.length} edges`}
                  emptyText={final ? "The answer read no graph nodes." : "No graph path read yet."}
                />
              ),
            },
            {
              id: "steps",
              label: `Steps (${live.toolCalls.length})`,
              content: <Steps live={live} />,
            },
            {
              id: "sources",
              label: `Sources (${sourceCount})`,
              content: <Sources live={live} final={final} />,
            },
          ]}
        />
      </aside>
    </div>
  );
}

function Steps({ live }: { live: Live }) {
  const [copiedStep, setCopiedStep] = useState<number | null>(null);
  if (live.toolCalls.length === 0) {
    return <p className="text-fg-secondary">{live.done ? "No tool was called for this answer." : "No tool called yet."}</p>;
  }
  async function copyTemplate(step: number, template: string) {
    try {
      await navigator.clipboard.writeText(template);
      setCopiedStep(step);
      setTimeout(() => setCopiedStep(null), 2000);
    } catch {
      setCopiedStep(null);
    }
  }
  return (
    <ol className="space-y-3">
      {live.toolCalls.map((t) => (
        <li key={t.step} className={cx("rounded-md border p-3", t.error ? "border-danger/40 bg-danger-subtle" : "border-border bg-surface-subtle")}>
          <p className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span>
              <span className="text-fg-muted">{t.step}.</span> <span className="font-mono font-medium">{t.name}</span>
            </span>
            <span className="tabular text-fg-secondary">
              {t.rows} row{t.rows === 1 ? "" : "s"}
              {t.truncated ? " (truncated)" : ""} · {ms(t.ms)}
            </span>
          </p>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs text-fg-secondary">
            {JSON.stringify(t.params, null, 2)}
          </pre>
          {t.error ? (
            <p className="mt-1 text-sm text-danger" role="note">
              {t.error}
            </p>
          ) : null}
          {t.template ? (
            <details className="mt-2">
              <summary className="cursor-pointer text-sm text-fg-secondary">Cypher template (read-only, parameterised)</summary>
              <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-surface p-2 font-mono text-xs">
                {t.template}
              </pre>
              <button
                type="button"
                onClick={() => void copyTemplate(t.step, t.template ?? "")}
                className="mt-2 inline-flex h-7 items-center gap-1 rounded-sm border border-border-input px-2 text-sm"
              >
                <Copy size={14} strokeWidth={1.5} aria-hidden="true" />
                {copiedStep === t.step ? "Copied" : "Copy template"}
              </button>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

function Sources({ live, final }: { live: Live; final: boolean }) {
  if (live.citations.length > 0) {
    return (
      <table className={tableClass}>
        <caption className="sr-only">Sources cited by the answer</caption>
        <thead>
          <tr>
            <th className={thClass}>#</th>
            <th className={thClass}>Source</th>
          </tr>
        </thead>
        <tbody>
          {live.citations.map((c) => (
            <tr key={c.index} id={`source-${c.index}`}>
              <td className={cx(tdClass, "font-mono")}>{c.index}</td>
              <td className={tdClass}>
                <span className="text-xs text-fg-muted">{c.label}</span>
                <br />
                <ExtLink href={c.url}>{c.title ?? c.key}</ExtLink>
                <span className="block font-mono text-xs break-all text-fg-muted">{c.key}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (live.evidence.length === 0) {
    return <p className="text-fg-secondary">{final ? "This answer cites no sources." : "No evidence read yet."}</p>;
  }
  return (
    <div>
      <p className="mb-2 text-xs text-fg-muted">
        Records read by the tool calls, in the order they were read. The answer&apos;s numbered markers refer to these records; the
        stream does not carry the numbering itself.
      </p>
      <table className={tableClass}>
        <caption className="sr-only">Evidence records read while answering</caption>
        <thead>
          <tr>
            <th className={thClass}>Type</th>
            <th className={thClass}>Record</th>
          </tr>
        </thead>
        <tbody>
          {live.evidence.map((c) => (
            <tr key={c.evidence_id}>
              <td className={cx(tdClass, "font-mono text-xs whitespace-nowrap")}>{c.source_type}</td>
              <td className={tdClass}>
                <ExtLink href={c.url}>{c.title ?? c.locator}</ExtLink>
                <span className="block font-mono text-xs break-all text-fg-muted">{c.locator}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
