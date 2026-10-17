"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";
import { PagerBar, usePaging } from "@/components/PagedTable";
import { routes } from "@/lib/routes";
import { SortHeader } from "@/components/SortHeader";
import { clientApi } from "@/lib/api/client";
import type { ApiFailure, ApiResult } from "@/lib/api/core";
import type { DecisionOut, Evidence, Finding, FindingDetail, IssueDraft, ItemList } from "@/lib/api/types";
import { FINDING_KIND_TEXT, humanize, isoDate, isoUtc, ms, numberFromPath, pluralS } from "@/lib/format";
import { kindLabel, toneColor } from "@/lib/kinds";
import { Chip, Dash, EmptyState, ErrorState, ExtLink, KepLink, PersonLink, SigLink, TableWrap, cx, tableClass, tdClass, thClass } from "./ui";

type Load<T> = { kind: "loading" } | { kind: "error"; error: ApiFailure } | { kind: "done"; data: T };
type Detail = Load<FindingDetail>;
type Decisions = Load<DecisionOut[]>;

type SortKey = "kep" | "sig" | "kind" | "state" | "detected" | "verdict";

const STATE_ORDER = ["open", "triaged", "drafted", "confirmed", "dismissed", "resolved_upstream"];

function stateRank(s: string): number {
  const i = STATE_ORDER.indexOf(s);
  return i < 0 ? STATE_ORDER.length : i;
}

function sigOf(f: Finding): string {
  return f.owning_sig ?? f.kep_path.split("/")[1] ?? "";
}

function kepNum(f: Finding): number | null {
  return f.kep_number ?? numberFromPath(f.kep_path);
}

function compare(a: Finding, b: Finding, key: SortKey): number {
  switch (key) {
    case "kep":
      return (kepNum(a) ?? 0) - (kepNum(b) ?? 0);
    case "sig":
      return sigOf(a).localeCompare(sigOf(b));
    case "kind":
      return a.kind.localeCompare(b.kind);
    case "state":
      return stateRank(a.state) - stateRank(b.state);
    case "detected":
      return (a.detected_at_iso ?? "").localeCompare(b.detected_at_iso ?? "");
    case "verdict":
      return (a.human_verdict ?? "~").localeCompare(b.human_verdict ?? "~");
  }
}

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

function verdictTone(v: string): "success" | "danger" | "neutral" {
  if (/^(correct|confirmed|true|yes)$/i.test(v)) return "success";
  if (/^(incorrect|wrong|false|no|rejected)$/i.test(v)) return "danger";
  return "neutral";
}

/** Findings as a sortable table whose rows expand (Enter or click) to both sides, who set each side, and the draft action (d). */
export function FindingsTable({
  items,
  selected,
  filtered,
  tones,
}: {
  items: Finding[];
  selected?: string;
  filtered: boolean;
  /** Series slot per kind, shared with the charts so a kind keeps its colour. */
  tones?: Record<string, number | null>;
}) {
  const base = useId();
  const router = useRouter();
  const tbodyRef = useRef<HTMLTableSectionElement>(null);
  // After a keyboard page change the focus moves to the first (or last) row of the new page.
  const focusAfterPage = useRef<"first" | "last" | null>(null);
  const [open, setOpen] = useState<Set<string>>(() => new Set(selected ? [selected] : []));
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const [decisions, setDecisions] = useState<Record<string, Decisions>>({});
  const [draft, setDraft] = useState<{ finding: Finding; opener: HTMLElement | null } | null>(null);
  const [sort, setSort] = useState<Sort>({ key: "state", dir: 1 });
  const anyVerdict = items.some((f) => f.human_verdict);
  const sorted = [...items].sort(
    (a, b) => compare(a, b, sort.key) * sort.dir || (kepNum(a) ?? 0) - (kepNum(b) ?? 0) || a.kind.localeCompare(b.kind),
  );
  const paging = usePaging(items.length);
  // A finding opened through ?finding= must be on the visible page (derived once per selected key).
  const [pagedFor, setPagedFor] = useState<string | undefined>(undefined);
  if (selected && pagedFor !== selected) {
    setPagedFor(selected);
    const idx = sorted.findIndex((f) => f.key === selected);
    if (idx >= 0) paging.setPage(Math.floor(idx / paging.size) + 1);
  }
  const pageRows = sorted.slice(paging.start, paging.end);

  useEffect(() => {
    const want = focusAfterPage.current;
    if (!want) return;
    focusAfterPage.current = null;
    const rows = tbodyRef.current?.querySelectorAll<HTMLTableRowElement>("tr[tabindex]");
    if (rows?.length) rows[want === "first" ? 0 : rows.length - 1].focus();
  }, [paging.page]);

  /** j/k move between finding rows; ] and [ change the page and land on its first or last row. */
  function rowKeys(e: React.KeyboardEvent<HTMLTableRowElement>): boolean {
    const rows = tbodyRef.current ? Array.from(tbodyRef.current.querySelectorAll<HTMLTableRowElement>("tr[tabindex]")) : [];
    const at = rows.indexOf(e.currentTarget);
    if (e.key === "j" || e.key === "k") {
      const next = rows[at + (e.key === "j" ? 1 : -1)];
      if (next) next.focus();
      else if (e.key === "j" && paging.page < paging.pages) {
        focusAfterPage.current = "first";
        paging.setPage(paging.page + 1);
      } else if (e.key === "k" && paging.page > 1) {
        focusAfterPage.current = "last";
        paging.setPage(paging.page - 1);
      }
      return true;
    }
    if (e.key === "]" && paging.page < paging.pages) {
      focusAfterPage.current = "first";
      paging.setPage(paging.page + 1);
      return true;
    }
    if (e.key === "[" && paging.page > 1) {
      focusAfterPage.current = "first";
      paging.setPage(paging.page - 1);
      return true;
    }
    return false;
  }

  // Results are stored from the callbacks only; a missing entry renders as loading.
  const fetchFor = (f: Finding, withEvidence: boolean, withDecisions: boolean) => {
    if (withEvidence) {
      clientApi.finding(f.key).then((res) => {
        setDetails((d) => ({ ...d, [f.key]: res.ok ? { kind: "done", data: res.data } : { kind: "error", error: res.error } }));
      });
    }
    const n = kepNum(f);
    if (withDecisions && n !== null) {
      clientApi.kepDecisions(n, f.kep_path).then((res: ApiResult<ItemList<DecisionOut>>) => {
        setDecisions((d) => ({
          ...d,
          [f.kep_path]: res.ok ? { kind: "done", data: res.data.items } : { kind: "error", error: res.error },
        }));
      });
    }
  };

  const load = (f: Finding) => {
    const needEvidence = !details[f.key];
    const needDecisions = !decisions[f.kep_path];
    if (needEvidence) setDetails((d) => ({ ...d, [f.key]: { kind: "loading" } }));
    if (needDecisions) setDecisions((d) => ({ ...d, [f.kep_path]: { kind: "loading" } }));
    fetchFor(f, needEvidence, needDecisions);
  };

  // A finding opened through ?finding= loads its evidence and scrolls into view.
  useEffect(() => {
    if (!selected) return;
    const f = items.find((x) => x.key === selected);
    if (!f) return;
    fetchFor(f, true, true);
    document.getElementById(`f-${encodeURIComponent(selected)}`)?.scrollIntoView({ block: "center" });
    // Only on first render for the selected finding.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  if (items.length === 0) {
    return (
      <EmptyState title={filtered ? "No findings match these filters" : "No records disagree"}>
        {filtered
          ? "No finding has the selected kind, SIG and state."
          : "The graph holds no Finding nodes: the detector has not run, or every kep.yaml agrees with its tracking issue and replacement declarations."}
      </EmptyState>
    );
  }
  function toggle(f: Finding) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(f.key)) next.delete(f.key);
      else next.add(f.key);
      return next;
    });
    if (!open.has(f.key)) load(f);
  }

  const cols = anyVerdict ? 9 : 8;

  return (
    <>
      <section className="rounded-md border border-border bg-surface" aria-labelledby={`${base}-t`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-3">
          <h3 id={`${base}-t`} className="text-md font-semibold">
            {items.length.toLocaleString("en-US")} finding{pluralS(items.length)}
          </h3>
          <p className="text-xs text-fg-muted">
            <kbd>Enter</kbd> or click expands a row · <kbd>j</kbd> <kbd>k</kbd> move · <kbd>o</kbd> opens the KEP ·{" "}
            <kbd>d</kbd> drafts a fix · <kbd>[</kbd> <kbd>]</kbd> change page · nothing on this page posts to GitHub
          </p>
        </div>
        <div className="px-4 pt-3">
          <PagerBar paging={paging} />
        </div>
        <TableWrap label="Findings table">
          <table className={tableClass}>
            <caption className="sr-only">Each finding with both disagreeing records; column headers sort</caption>
            <thead>
              <tr>
                <th className={cx(thClass, "w-8")}>
                  <span className="sr-only">Expand</span>
                </th>
                <SortHead sort={sort} onSort={setSort} k="kep">KEP</SortHead>
                <SortHead sort={sort} onSort={setSort} k="sig">SIG</SortHead>
                <SortHead sort={sort} onSort={setSort} k="kind">Kind</SortHead>
                <th className={thClass}>Record A</th>
                <th className={thClass}>Record B</th>
                <th className={thClass}>Suggested fix</th>
                {anyVerdict ? <SortHead sort={sort} onSort={setSort} k="verdict">Hand check</SortHead> : null}
                <SortHead sort={sort} onSort={setSort} k="state">State</SortHead>
              </tr>
            </thead>
            <tbody ref={tbodyRef}>
              {pageRows.map((f, i) => {
                const n = kepNum(f);
                const expanded = open.has(f.key);
                const panelId = `${base}-panel-${i}`;
                const tone = tones?.[f.kind] ?? null;
                return [
                  <tr
                    key={f.key}
                    id={`f-${encodeURIComponent(f.key)}`}
                    tabIndex={0}
                    aria-expanded={expanded}
                    onClick={(e) => {
                      if ((e.target as HTMLElement).closest("a, button")) return;
                      toggle(f);
                    }}
                    onKeyDown={(e) => {
                      if (e.target !== e.currentTarget) return;
                      if (e.altKey || e.ctrlKey || e.metaKey) return;
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggle(f);
                      } else if (e.key === "d") {
                        e.preventDefault();
                        setDraft({ finding: f, opener: e.currentTarget });
                      } else if (e.key === "o" && n !== null) {
                        e.preventDefault();
                        router.push(routes.kepPath(n, f.kep_path));
                      } else if (rowKeys(e)) {
                        e.preventDefault();
                      }
                    }}
                    className={cx("cursor-pointer hover:bg-surface-subtle", selected === f.key && "bg-accent-subtle", expanded && "bg-surface-subtle")}
                  >
                    <td className={cx(tdClass, "pr-0")}>
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={panelId}
                        aria-label={`${expanded ? "Collapse" : "Expand"} ${n !== null ? `KEP-${n}` : f.kep_path} ${f.kind}`}
                        onClick={() => toggle(f)}
                        className="flex h-6 w-6 items-center justify-center rounded-sm text-fg-secondary hover:text-fg"
                      >
                        {expanded ? (
                          <ChevronDown size={16} strokeWidth={1.5} aria-hidden="true" />
                        ) : (
                          <ChevronRight size={16} strokeWidth={1.5} aria-hidden="true" />
                        )}
                      </button>
                    </td>
                    <td className={cx(tdClass, "min-w-48")}>
                      <KepLink number={n} label={n !== null ? `KEP-${n}` : f.kep_path} />
                      {f.kep_title ? <p className="text-xs">{f.kep_title}</p> : null}
                    </td>
                    <td className={cx(tdClass, "whitespace-nowrap")}>{sigOf(f) ? <SigLink sig={sigOf(f)} /> : <Dash />}</td>
                    <td className={cx(tdClass, "min-w-48")} title={FINDING_KIND_TEXT[f.kind]}>
                      <span className="inline-flex items-center gap-2">
                        <span aria-hidden="true" className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: toneColor(tone) }} />
                        <span>{kindLabel(f.kind)}</span>
                      </span>
                      <span className="ident block pl-[18px] text-xs text-fg-muted">{f.kind}</span>
                    </td>
                    <td className={cx(tdClass, "min-w-40")}>
                      <Side label={f.a_label} value={f.a_value} url={f.a_url} />
                    </td>
                    <td className={cx(tdClass, "min-w-40")}>
                      <Side label={f.b_label} value={f.b_value} url={f.b_url} />
                    </td>
                    <td className={cx(tdClass, "min-w-36")}>
                      {f.suggested_fix ? <span className="text-sm">{humanize(f.suggested_fix)}</span> : <Dash />}
                    </td>
                    {anyVerdict ? (
                      <td className={tdClass}>
                        {f.human_verdict ? <Chip tone={verdictTone(f.human_verdict)}>{f.human_verdict}</Chip> : <span className="text-xs text-fg-muted">not checked</span>}
                      </td>
                    ) : null}
                    <td className={tdClass}>
                      <Chip tone={f.state === "open" ? "warning" : f.state === "dismissed" ? "neutral" : "accent"}>{f.state}</Chip>
                      {f.detected_at_iso ? <p className="mt-1 font-mono text-xs whitespace-nowrap text-fg-muted">{isoDate(f.detected_at_iso)}</p> : null}
                    </td>
                  </tr>,
                  expanded ? (
                    <tr key={`${f.key}#panel`} id={panelId}>
                      <td colSpan={cols} className="border-b border-border bg-surface-subtle px-3 py-3">
                        <FindingPanel
                          finding={f}
                          detail={details[f.key]}
                          decisions={decisions[f.kep_path]}
                          onDraft={(el) => setDraft({ finding: f, opener: el })}
                        />
                      </td>
                    </tr>
                  ) : null,
                ];
              })}
            </tbody>
          </table>
        </TableWrap>
      </section>
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

type Sort = { key: SortKey; dir: 1 | -1 };

function SortHead({
  k,
  sort,
  onSort,
  children,
}: {
  k: SortKey;
  sort: Sort;
  onSort: (f: (s: Sort) => Sort) => void;
  children: React.ReactNode;
}) {
  return (
    <SortHeader
      active={sort.key === k}
      dir={sort.dir}
      onClick={() => onSort((s) => ({ key: k, dir: s.key === k ? (s.dir === 1 ? -1 : 1) : 1 }))}
    >
      {children}
    </SortHeader>
  );
}

type SideKey = "a" | "b";

/** Which side a status-change record belongs to: the record whose URL is of the same kind (file or issue). */
function sideOf(e: Evidence, f: Finding): SideKey | null {
  const isIssue = (u: string | null) => Boolean(u && /\/issues\/\d+/.test(u));
  const isFile = (u: string | null) => Boolean(u && /\/(blob|tree)\//.test(u));
  const evIssue = isIssue(e.url) || /:(label|milestone):/.test(e.key);
  if (evIssue) return isIssue(f.a_url) ? "a" : isIssue(f.b_url) ? "b" : null;
  if (isFile(e.url)) return isFile(f.a_url) ? "a" : isFile(f.b_url) ? "b" : null;
  return null;
}

function ByRole({ d }: { d: DecisionOut }) {
  const roles = new Map<string, string[]>();
  for (const x of d.deciders) roles.set(x.role, [...(roles.get(x.role) ?? []), x.login]);
  return (
    <ul className="mt-1 space-y-0.5 text-xs">
      {[...roles.entries()].map(([role, logins]) => (
        <li key={role} className="flex flex-wrap gap-x-2">
          <span className="w-28 shrink-0 text-fg-muted">{role.replace(/_/g, " ")}</span>
          {[...new Set(logins)].map((l) => (
            <PersonLink key={l} login={l} />
          ))}
        </li>
      ))}
    </ul>
  );
}

function WhoSet({ side, finding, detail, decisions }: { side: SideKey; finding: Finding; detail: Detail | undefined; decisions: Decisions | undefined }) {
  if (!detail || detail.kind === "loading") {
    return (
      <div role="status" className="mt-2 space-y-1">
        <span className="sr-only">Loading who set this value</span>
        <div className="skeleton h-3 w-9/12" />
        <div className="skeleton h-3 w-7/12" />
      </div>
    );
  }
  if (detail.kind === "error") return null;
  const changes = detail.data.evidence.filter((e) => e.label === "StatusChange" && sideOf(e, finding) === side);
  if (changes.length === 0) {
    return <p className="mt-2 text-xs text-fg-muted">The graph holds no change record that set this value.</p>;
  }
  return (
    <ul className="mt-2 space-y-2 border-t border-border pt-2">
      {changes.map((c) => {
        const ds = decisions?.kind === "done" ? decisions.data.filter((d) => d.evidence.some((e) => e.key === c.key)) : [];
        return (
          <li key={c.key}>
            <ExtLink href={c.url} className="text-xs">
              <span className="ident">{c.title ?? c.key}</span>
            </ExtLink>
            {decisions?.kind === "loading" ? <p className="text-xs text-fg-muted">Loading decisions</p> : null}
            {ds.map((d) => (
              <div key={d.key} className="mt-1">
                {d.summary ? <p className="text-xs text-fg-secondary">{d.summary}</p> : null}
                <ByRole d={d} />
                {d.decided_at_iso ? <p className="ident mt-0.5 text-xs text-fg-muted">decided {isoUtc(d.decided_at_iso)}</p> : null}
              </div>
            ))}
            {decisions?.kind === "done" && ds.length === 0 ? (
              <p className="text-xs text-fg-muted">No decision with approvers is linked to this change.</p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function FindingPanel({
  finding,
  detail,
  decisions,
  onDraft,
}: {
  finding: Finding;
  detail: Detail | undefined;
  decisions: Decisions | undefined;
  onDraft: (opener: HTMLElement) => void;
}) {
  const sides: { key: SideKey; label: string; value: string | null; url: string | null }[] = [
    { key: "a", label: finding.a_label, value: finding.a_value, url: finding.a_url },
    { key: "b", label: finding.b_label, value: finding.b_value, url: finding.b_url },
  ];
  return (
    <div className="grid gap-5 lg:grid-cols-12">
      <div className="space-y-4 lg:col-span-8">
        <div>
          <p className="eyebrow">{kindLabel(finding.kind)}</p>
          {FINDING_KIND_TEXT[finding.kind] ? <p className="mt-1 max-w-[60ch] text-md">{FINDING_KIND_TEXT[finding.kind]}</p> : null}
        </div>
        <div className="grid border-y border-border-strong sm:grid-cols-2 sm:divide-x sm:divide-border">
          {sides.map((s) => (
            <div key={s.key} className="py-3 first:pr-4 last:border-t last:border-border last:pt-3 sm:last:border-t-0 sm:last:pl-4">
              <p className="eyebrow mb-1">Record {s.key.toUpperCase()} · who set it</p>
              <Side label={s.label} value={s.value} url={s.url} />
              <WhoSet side={s.key} finding={finding} detail={detail} decisions={decisions} />
            </div>
          ))}
        </div>
        <div>
          <p className="eyebrow">Evidence records</p>
          <EvidenceList detail={detail} />
        </div>
        <p className="text-xs text-fg-muted">
          Finding key <span className="font-mono break-all">{finding.key}</span>
          {finding.detected_at_iso ? (
            <>
              {" "}
              · detected <span className="font-mono">{isoUtc(finding.detected_at_iso)}</span>
            </>
          ) : null}
        </p>
      </div>
      <div className="space-y-3 lg:col-span-4">
        <div className="rounded-md border border-border bg-surface p-3">
          <p className="eyebrow">Hand check</p>
          {finding.human_verdict ? (
            <>
              <p className="mt-1">
                <Chip tone={verdictTone(finding.human_verdict)}>{finding.human_verdict}</Chip>
              </p>
              {finding.human_checked_by || finding.human_checked_at ? (
                <p className="mt-1 text-xs text-fg-muted">
                  {finding.human_checked_by ? `by ${finding.human_checked_by}` : ""}
                  {finding.human_checked_at ? ` on ${isoDate(finding.human_checked_at)}` : ""}
                </p>
              ) : null}
              {finding.human_note ? <p className="mt-1 text-sm text-fg-secondary">{finding.human_note}</p> : null}
            </>
          ) : (
            <p className="mt-1 text-sm text-fg-secondary">Not hand-checked yet.</p>
          )}
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <p className="eyebrow">Agent triage (advisory)</p>
          {finding.triage_verdict || finding.assessment ? (
            <>
              {finding.triage_verdict ? (
                <p className="mt-1">
                  Verdict <span className="font-mono">{finding.triage_verdict}</span>
                </p>
              ) : null}
              {finding.assessment ? <p className="mt-1 text-sm text-fg-secondary">{finding.assessment}</p> : null}
            </>
          ) : (
            <p className="mt-1 text-sm text-fg-secondary">Not triaged: the freshness agent has not assessed this finding.</p>
          )}
        </div>
        <div className="rounded-md border border-border bg-surface p-3">
          <p className="eyebrow">Fix</p>
          <p className="mt-1 text-sm">
            Suggested {finding.suggested_fix ? <span className="font-medium">{humanize(finding.suggested_fix).toLowerCase()}</span> : <Dash />}
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
          <span className="w-24 shrink-0 font-mono text-xs text-fg-muted">{e.label}</span>
          <ExtLink href={e.url}>{e.title ?? e.key}</ExtLink>
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
              {state.draft.evidence_keys.length} evidence record{pluralS(state.draft.evidence_keys.length)} listed · composed in {ms(state.ms)} ·
              tool <span className="font-mono">draft_stale_doc_issue</span>
            </p>
          </>
        ) : null}
      </div>
    </dialog>
  );
}
