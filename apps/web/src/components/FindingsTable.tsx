"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { clientApi } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/core";
import type { Evidence, Finding, FindingDetail, IssueDraft } from "@/lib/api/types";
import { FINDING_KIND_TEXT, humanize, isoDate, numberFromPath } from "@/lib/format";
import { Card, Chip, Dash, EmptyState, ErrorState, ExtLink, KepLink, TableWrap, cx, tableClass, tdClass, thClass } from "./ui";

type Detail = { kind: "loading" } | { kind: "error"; error: ApiFailure } | { kind: "done"; data: FindingDetail };

function Side({ label, value, url }: { label: string; value: string | null; url: string | null }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-fg-muted">{label}</p>
      <p className="font-mono text-sm break-words">{value ?? <Dash />}</p>
      {url ? (
        <ExtLink href={url} className="text-xs">
          source
        </ExtLink>
      ) : null}
    </div>
  );
}

/** Findings as a table whose rows expand (Enter or click) to both sides, the evidence records and the draft action (d). */
export function FindingsTable({ items, selected, filtered }: { items: Finding[]; selected?: string; filtered: boolean }) {
  const base = useId();
  const [open, setOpen] = useState<Set<string>>(() => new Set(selected ? [selected] : []));
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const [draft, setDraft] = useState<{ finding: Finding; opener: HTMLElement | null } | null>(null);

  if (items.length === 0) {
    return (
      <EmptyState title={filtered ? "No findings match these filters" : "No findings in the graph"}>
        {filtered
          ? "No finding has the selected kind, SIG and state."
          : "The graph holds no Finding nodes: the detector has not run, or every check passed."}
      </EmptyState>
    );
  }
  const sorted = [...items].sort((a, b) => (a.kep_number ?? 0) - (b.kep_number ?? 0) || a.kind.localeCompare(b.kind));

  function load(key: string) {
    if (details[key]) return;
    setDetails((d) => ({ ...d, [key]: { kind: "loading" } }));
    clientApi.finding(key).then((res) => {
      setDetails((d) => ({ ...d, [key]: res.ok ? { kind: "done", data: res.data } : { kind: "error", error: res.error } }));
    });
  }

  function toggle(key: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else {
        next.add(key);
        load(key);
      }
      return next;
    });
  }

  return (
    <>
      <Card title={`Findings (${items.length})`} id="findings">
        <p className="mb-3 text-sm text-fg-secondary">
          Enter or click expands a row; d opens the draft for the focused row. Nothing on this page posts to GitHub.
        </p>
        <TableWrap label="Findings table">
          <table className={tableClass}>
            <caption className="sr-only">Each finding with both disagreeing sources</caption>
            <thead>
              <tr>
                <th className={cx(thClass, "w-8")}>
                  <span className="sr-only">Expand</span>
                </th>
                <th className={thClass}>KEP</th>
                <th className={thClass}>Kind</th>
                <th className={thClass}>Side A</th>
                <th className={thClass}>Side B</th>
                <th className={thClass}>Suggested fix</th>
                <th className={thClass}>State</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((f, i) => {
                const n = f.kep_number ?? numberFromPath(f.kep_path);
                const expanded = open.has(f.key);
                const panelId = `${base}-panel-${i}`;
                return [
                  <tr
                    key={f.key}
                    id={`f-${encodeURIComponent(f.key)}`}
                    tabIndex={0}
                    aria-expanded={expanded}
                    onClick={(e) => {
                      if ((e.target as HTMLElement).closest("a, button")) return;
                      toggle(f.key);
                    }}
                    onKeyDown={(e) => {
                      if (e.target !== e.currentTarget) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggle(f.key);
                      } else if (e.key === "d") {
                        e.preventDefault();
                        setDraft({ finding: f, opener: e.currentTarget });
                      }
                    }}
                    className={cx("cursor-pointer", selected === f.key && "bg-accent-subtle", expanded && "bg-surface-subtle")}
                  >
                    <td className={cx(tdClass, "pr-0")}>
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={panelId}
                        aria-label={`${expanded ? "Collapse" : "Expand"} ${n !== null ? `KEP-${n}` : f.kep_path} ${f.kind}`}
                        onClick={() => toggle(f.key)}
                        className="flex h-6 w-6 items-center justify-center rounded-sm text-fg-secondary hover:text-fg"
                      >
                        {expanded ? (
                          <ChevronDown size={16} strokeWidth={1.5} aria-hidden="true" />
                        ) : (
                          <ChevronRight size={16} strokeWidth={1.5} aria-hidden="true" />
                        )}
                      </button>
                    </td>
                    <td className={cx(tdClass, "min-w-40")}>
                      <KepLink number={n} label={n !== null ? `KEP-${n}` : f.kep_path} />
                      {f.kep_title ? <p className="text-xs">{f.kep_title}</p> : null}
                      {f.owning_sig ? <p className="font-mono text-xs text-fg-muted">{f.owning_sig}</p> : null}
                    </td>
                    <td className={cx(tdClass, "min-w-44")}>
                      <span className="font-mono">{f.kind}</span>
                      {FINDING_KIND_TEXT[f.kind] ? <p className="mt-0.5 text-xs text-fg-muted">{FINDING_KIND_TEXT[f.kind]}</p> : null}
                    </td>
                    <td className={cx(tdClass, "min-w-40")}>
                      <Side label={f.a_label} value={f.a_value} url={f.a_url} />
                    </td>
                    <td className={cx(tdClass, "min-w-40")}>
                      <Side label={f.b_label} value={f.b_value} url={f.b_url} />
                    </td>
                    <td className={cx(tdClass, "min-w-40")}>
                      {f.suggested_fix ? <span className="font-mono text-sm">{humanize(f.suggested_fix)}</span> : <Dash />}
                      {f.triage_verdict ? (
                        <p className="mt-1 text-xs text-fg-secondary">
                          Agent verdict: <span className="font-mono">{f.triage_verdict}</span>
                        </p>
                      ) : null}
                    </td>
                    <td className={tdClass}>
                      <Chip tone={f.state === "open" ? "warning" : f.state === "dismissed" ? "neutral" : "accent"}>{f.state}</Chip>
                      {f.detected_at_iso ? <p className="mt-1 font-mono text-xs text-fg-muted">{isoDate(f.detected_at_iso)}</p> : null}
                    </td>
                  </tr>,
                  expanded ? (
                    <tr key={`${f.key}#panel`} id={panelId}>
                      <td colSpan={7} className="border-b border-border bg-surface-subtle px-3 py-3">
                        <FindingPanel finding={f} detail={details[f.key]} onDraft={(el) => setDraft({ finding: f, opener: el })} />
                      </td>
                    </tr>
                  ) : null,
                ];
              })}
            </tbody>
          </table>
        </TableWrap>
      </Card>
      {draft ? (
        <DraftFixDialog
          finding={draft.finding}
          onClose={() => {
            const el = draft.opener;
            setDraft(null);
            el?.focus();
          }}
        />
      ) : null}
    </>
  );
}

function FindingPanel({ finding, detail, onDraft }: { finding: Finding; detail: Detail | undefined; onDraft: (opener: HTMLElement) => void }) {
  return (
    <div className="grid gap-4 lg:grid-cols-12">
      <div className="space-y-3 lg:col-span-7">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-border bg-surface p-3">
            <p className="mb-1 text-xs font-medium text-fg-secondary">Side A</p>
            <Side label={finding.a_label} value={finding.a_value} url={finding.a_url} />
          </div>
          <div className="rounded-md border border-border bg-surface p-3">
            <p className="mb-1 text-xs font-medium text-fg-secondary">Side B</p>
            <Side label={finding.b_label} value={finding.b_value} url={finding.b_url} />
          </div>
        </div>
        <div>
          <p className="text-xs font-medium text-fg-secondary">Evidence records</p>
          <EvidenceList detail={detail} />
        </div>
        <p className="text-xs text-fg-muted">
          Finding key <span className="font-mono break-all">{finding.key}</span>
          {finding.detected_at_iso ? (
            <>
              {" "}
              · detected <span className="font-mono">{isoDate(finding.detected_at_iso)}</span>
            </>
          ) : null}
        </p>
      </div>
      <div className="space-y-3 lg:col-span-5">
        <div className="rounded-md border border-border bg-surface p-3">
          <p className="text-xs font-medium text-fg-secondary">Triage (advisory, not a human check)</p>
          {finding.triage_verdict || finding.assessment ? (
            <>
              {finding.triage_verdict ? (
                <p className="mt-1">
                  Verdict: <span className="font-mono">{finding.triage_verdict}</span>
                </p>
              ) : null}
              {finding.assessment ? <p className="mt-1 text-sm text-fg-secondary">{finding.assessment}</p> : null}
              <p className="mt-1 text-xs text-fg-muted">Written by the freshness agent from the two sources above; a human verdict is not recorded in the graph.</p>
            </>
          ) : (
            <p className="mt-1 text-sm text-fg-secondary">Not triaged yet: the freshness agent has not assessed this finding.</p>
          )}
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <p className="text-xs font-medium text-fg-secondary">Fix</p>
          <p className="mt-1 text-sm">
            Suggested: {finding.suggested_fix ? <span className="font-mono">{humanize(finding.suggested_fix)}</span> : <Dash />}
          </p>
          <button
            type="button"
            onClick={(e) => onDraft(e.currentTarget)}
            className="mt-2 h-8 rounded-sm border border-border-input bg-surface px-3 text-base font-medium hover:border-border-strong"
          >
            Draft fix
          </button>
          <p className="mt-1 text-xs text-fg-muted">Composes an issue draft from the evidence. Nothing is posted.</p>
        </div>
      </div>
    </div>
  );
}

function EvidenceList({ detail }: { detail: Detail | undefined }) {
  if (!detail || detail.kind === "loading") {
    return (
      <div role="status" className="mt-1 space-y-1">
        <span className="sr-only">Loading evidence</span>
        <div className="skeleton h-4 w-10/12" />
        <div className="skeleton h-4 w-8/12" />
      </div>
    );
  }
  if (detail.kind === "error") return <ErrorState error={detail.error} what="Evidence" />;
  const items: Evidence[] = detail.data.evidence;
  if (items.length === 0) return <p className="mt-1 text-sm text-fg-secondary">The finding has no EVIDENCED_BY records beyond the two sides.</p>;
  return (
    <ul className="mt-1 space-y-1">
      {items.map((e) => (
        <li key={e.evidence_id} className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span className="font-mono text-xs text-fg-muted">{e.label}</span>
          <ExtLink href={e.url}>{e.title ?? e.key}</ExtLink>
          <span className="font-mono text-xs break-all text-fg-muted">{e.key}</span>
        </li>
      ))}
    </ul>
  );
}

type DraftState = { kind: "loading" } | { kind: "error"; error: ApiFailure } | { kind: "missing" } | { kind: "done"; draft: IssueDraft; ms: number };

function isDraft(row: Record<string, unknown> | undefined): row is Record<string, unknown> & IssueDraft {
  return Boolean(row && typeof row.title === "string" && typeof row.body === "string" && typeof row.target_repo === "string");
}

/** Native dialog: focus stays inside, Escape closes. Calls the draft tool once on open. */
function DraftFixDialog({ finding, onClose }: { finding: Finding; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<DraftState>({ kind: "loading" });
  const [copied, setCopied] = useState<"title" | "body" | null>(null);
  const titleId = useId();
  const n = finding.kep_number ?? numberFromPath(finding.kep_path);

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    clientApi.draftIssue(finding.key, ctrl.signal).then((res) => {
      if (ctrl.signal.aborted) return;
      if (!res.ok) {
        setState({ kind: "error", error: res.error });
        return;
      }
      const row = res.data.rows[0];
      if (!row || row.not_found === true || !isDraft(row)) {
        setState({ kind: "missing" });
        return;
      }
      setState({ kind: "done", draft: row, ms: res.data.ms });
    });
    return () => ctrl.abort();
  }, [finding.key]);

  async function copy(kind: "title" | "body", value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      setCopied(null);
    }
  }

  const copyButton = "inline-flex h-7 items-center gap-1 rounded-sm border border-border-input bg-surface px-2 text-sm";

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[min(100vw-32px,760px)] rounded-md border border-border bg-surface p-0 text-fg backdrop:bg-scrim"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h2 id={titleId} className="text-md font-semibold">
            Draft a fix for {n !== null ? `KEP-${n}` : finding.kep_path}
          </h2>
          <p className="mt-0.5 text-sm text-fg-secondary">
            <span className="font-mono">{finding.kind}</span> · composed by code from the finding&apos;s evidence, no language model
          </p>
        </div>
        <button type="button" onClick={() => ref.current?.close()} className="h-8 rounded-sm border border-border-input px-3 text-base">
          Close
        </button>
      </div>
      <div className="space-y-3 p-4">
        <p className="rounded-md bg-warning-subtle p-3 text-sm">
          Nothing is posted. This page and the API only compose the text; copy it and open the issue yourself if you agree
          with it. Nothing here writes to kubernetes/* repositories.
        </p>
        {state.kind === "loading" ? (
          <div role="status" className="space-y-2">
            <span className="sr-only">Composing the draft</span>
            <div className="skeleton h-4 w-8/12" />
            <div className="skeleton h-32 w-full" />
          </div>
        ) : null}
        {state.kind === "error" ? <ErrorState error={state.error} what="Draft" /> : null}
        {state.kind === "missing" ? (
          <EmptyState title="No draft">The API found no finding with this key, so there is nothing to draft.</EmptyState>
        ) : null}
        {state.kind === "done" ? (
          <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-fg-secondary">Where a human would file it</dt>
                <dd className="font-mono">{state.draft.target_repo}</dd>
              </div>
              <div>
                <dt className="text-fg-secondary">Status</dt>
                <dd>
                  <span className="font-mono">{state.draft.status}</span>
                  {state.draft.posted ? null : <span className="text-fg-muted"> · not posted</span>}
                </dd>
              </div>
            </dl>
            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <label htmlFor={`${titleId}-t`} className="text-sm text-fg-secondary">
                  Title
                </label>
                <button type="button" onClick={() => void copy("title", state.draft.title)} className={copyButton}>
                  <Copy size={14} strokeWidth={1.5} aria-hidden="true" />
                  {copied === "title" ? "Copied" : "Copy title"}
                </button>
              </div>
              <input
                id={`${titleId}-t`}
                readOnly
                value={state.draft.title}
                className="block w-full rounded-sm border border-border bg-surface-subtle px-2 py-1 font-mono text-sm"
              />
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <label htmlFor={`${titleId}-b`} className="text-sm text-fg-secondary">
                  Body (Markdown, read-only)
                </label>
                <button type="button" onClick={() => void copy("body", state.draft.body)} className={copyButton}>
                  <Copy size={14} strokeWidth={1.5} aria-hidden="true" />
                  {copied === "body" ? "Copied" : "Copy body"}
                </button>
              </div>
              <textarea
                id={`${titleId}-b`}
                readOnly
                value={state.draft.body}
                rows={Math.min(18, state.draft.body.split("\n").length + 1)}
                className="block w-full resize-y rounded-sm border border-border bg-surface-subtle p-2 font-mono text-xs"
              />
            </div>
            <p className="text-xs text-fg-muted">
              {state.draft.evidence_keys.length} evidence record{state.draft.evidence_keys.length === 1 ? "" : "s"} listed · composed in {Math.round(state.ms)} ms ·
              tool <span className="font-mono">draft_stale_doc_issue</span>
            </p>
          </>
        ) : null}
      </div>
    </dialog>
  );
}
