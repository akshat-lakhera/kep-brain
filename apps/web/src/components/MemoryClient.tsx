"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import { clientApi } from "@/lib/api/client";
import type { ApiResult } from "@/lib/api/core";
import type { AgentsBoard, MemoryMe } from "@/lib/api/types";
import { MEMORY_KEY, getMemoryId, resetMemoryId } from "@/lib/memory";
import { RowsTable, asRows } from "./DataView";
import { Tabs } from "./Tabs";
import { EmptyState, ErrorState, Notice, SkeletonBlock } from "./ui";

const idListeners = new Set<() => void>();

function subscribeId(cb: () => void) {
  idListeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === MEMORY_KEY) cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    idListeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

function notifyId() {
  idListeners.forEach((l) => l());
}

export function MemoryClient() {
  const memoryId = useSyncExternalStore(subscribeId, getMemoryId, () => null);
  const [reveal, setReveal] = useState(false);
  const [mem, setMem] = useState<ApiResult<MemoryMe> | null>(null);
  const [board, setBoard] = useState<ApiResult<AgentsBoard> | null>(null);
  const [version, setVersion] = useState(0);
  const [forgetMsg, setForgetMsg] = useState<ApiResult<{ deleted: boolean }> | null>(null);

  useEffect(() => {
    let live = true;
    clientApi.memoryMe().then((r) => {
      if (live) setMem(r);
    });
    clientApi.agentsBoard().then((r) => {
      if (live) setBoard(r);
    });
    return () => {
      live = false;
    };
  }, [version, memoryId]);

  function reload() {
    setMem(null);
    setBoard(null);
    setVersion((v) => v + 1);
  }

  async function forget() {
    if (!window.confirm("Delete everything stored for this anonymous id? This cannot be undone.")) return;
    const r = await clientApi.forgetMemory();
    setForgetMsg(r);
    reload();
  }

  const masked = memoryId ? `mem_${memoryId.slice(0, 6)}…` : "unavailable";
  const btn = "h-8 rounded-sm border border-border-input bg-surface px-3 text-base hover:border-border-strong";

  return (
    <div className="space-y-6">
      <section aria-label="Identity" className="rounded-md border border-border bg-surface p-4">
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-fg-secondary">Anonymous id</span>
          <span className="font-mono">{reveal && memoryId ? `mem_${memoryId}` : masked}</span>
          {memoryId ? (
            <button type="button" className="quiet-link text-sm" aria-pressed={reveal} onClick={() => setReveal((v) => !v)}>
              {reveal ? "Hide" : "Reveal"}
            </button>
          ) : null}
        </p>
        <p className="mt-1 max-w-[80ch] text-sm text-fg-secondary">
          Generated in this browser, stored under <span className="font-mono">{MEMORY_KEY}</span>, sent as the{" "}
          <span className="font-mono">X-Kep-Memory-Id</span> header and never placed in a URL. Another browser profile is
          another tenant.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            className={btn}
            onClick={() => {
              resetMemoryId();
              notifyId();
              setForgetMsg(null);
              reload();
            }}
          >
            New identity
          </button>
          <button type="button" className={`${btn} text-danger`} onClick={() => void forget()}>
            Forget everything
          </button>
        </div>
        {forgetMsg ? (
          <div className="mt-3" aria-live="polite">
            {forgetMsg.ok ? (
              <p className="text-sm text-success">Memory for this id deleted.</p>
            ) : (
              <ErrorState error={forgetMsg.error} what="Forget" />
            )}
          </div>
        ) : null}
      </section>

      <Tabs
        label="Memory"
        tabs={[
          { id: "mine", label: "Your memory", content: <Mine result={mem} onRetry={reload} /> },
          { id: "shared", label: "Shared findings", content: <Shared result={board} onRetry={reload} /> },
          { id: "queue", label: "Task queue", content: <Queue result={board} onRetry={reload} /> },
        ]}
      />
    </div>
  );
}

function Retry({ onRetry }: { onRetry: () => void }) {
  return (
    <button type="button" onClick={onRetry} className="h-8 rounded-sm border border-border-input bg-surface px-3">
      Retry
    </button>
  );
}

const MINE: { key: keyof MemoryMe; title: string; empty: string }[] = [
  { key: "recent_episodes", title: "Episodes", empty: "Each question you ask on the Ask page is kept here with a short answer summary." },
  { key: "facts", title: "Facts", empty: "Interests learned from your questions (the SIGs and KEPs you return to) appear here." },
  { key: "procedures", title: "Procedures", empty: "The tool sequences that answered your kinds of questions appear here." },
  { key: "sessions", title: "Sessions", empty: "Each visit that asked at least one question appears here." },
];

function Mine({ result, onRetry }: { result: ApiResult<MemoryMe> | null; onRetry: () => void }) {
  if (!result) return <SkeletonBlock lines={4} label="Loading your memory" />;
  if (!result.ok) {
    if (result.error.code === "memory_unavailable")
      return <Notice>Memory is unavailable right now; Ask continues without recall.</Notice>;
    return (
      <ErrorState error={result.error} what="Your memory">
        <Retry onRetry={onRetry} />
      </ErrorState>
    );
  }
  return (
    <div className="space-y-6">
      {MINE.map(({ key, title, empty }) => {
        const rows = asRows(result.data[key]);
        return (
          <section key={String(key)} aria-label={title}>
            <h3 className="mb-2 font-semibold">
              {title} ({rows.length})
            </h3>
            {rows.length ? <RowsTable rows={rows} caption={title} maxCols={6} /> : <EmptyState title={`No ${title.toLowerCase()} yet`}>{empty}</EmptyState>}
          </section>
        );
      })}
    </div>
  );
}

function Shared({ result, onRetry }: { result: ApiResult<AgentsBoard> | null; onRetry: () => void }) {
  if (!result) return <SkeletonBlock lines={4} label="Loading shared findings" />;
  if (!result.ok)
    return (
      <ErrorState error={result.error} what="Shared findings">
        <Retry onRetry={onRetry} />
      </ErrorState>
    );
  const rows = asRows(result.data.findings_recent);
  return (
    <div className="space-y-3">
      <p className="max-w-[80ch] text-fg-secondary">
        Written by the detector and the triage agent; read by the answering agent and MCP clients. Full list:{" "}
        <Link href="/audit" className="prose-link">
          Audit
        </Link>
        .
      </p>
      {rows.length ? (
        <RowsTable rows={rows} caption="Recently written or updated findings" />
      ) : (
        <EmptyState title="No recent finding activity">Findings written or triaged by the agents appear here.</EmptyState>
      )}
    </div>
  );
}

function Queue({ result, onRetry }: { result: ApiResult<AgentsBoard> | null; onRetry: () => void }) {
  if (!result) return <SkeletonBlock lines={4} label="Loading the task queue" />;
  if (!result.ok)
    return (
      <ErrorState error={result.error} what="Task queue">
        <Retry onRetry={onRetry} />
      </ErrorState>
    );
  const agents = asRows(result.data.agents);
  const tasks = asRows(result.data.tasks);
  const handoffs = asRows(result.data.handoffs_last_hour);
  return (
    <div className="space-y-6">
      <section aria-label="Agents">
        <h3 className="mb-2 font-semibold">Agents ({agents.length})</h3>
        {agents.length ? <RowsTable rows={agents} caption="Agents and jobs" /> : <EmptyState title="No agent has reported in" />}
      </section>
      <section aria-label="Tasks">
        <h3 className="mb-2 font-semibold">Tasks ({tasks.length})</h3>
        {tasks.length ? <RowsTable rows={tasks} caption="Tasks" /> : <EmptyState title="No tasks queued" />}
      </section>
      <section aria-label="Handoffs in the last hour">
        <h3 className="mb-2 font-semibold">Handoffs in the last hour ({handoffs.length})</h3>
        {handoffs.length ? <RowsTable rows={handoffs} caption="Handoffs in the last hour" /> : <EmptyState title="No handoffs in the last hour" />}
      </section>
    </div>
  );
}
