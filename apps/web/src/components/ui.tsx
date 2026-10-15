import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, CircleDot, ExternalLink, XCircle } from "lucide-react";
import type { ApiFailure } from "@/lib/api/core";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function PageHeader({ title, lead, children }: { title: ReactNode; lead?: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-6">
      <h1 className="text-lg font-semibold">{title}</h1>
      {lead ? <p className="mt-1 max-w-[80ch] text-fg-secondary">{lead}</p> : null}
      {children}
    </header>
  );
}

export function Card({
  title,
  id,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  id?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={cx("rounded-md border border-border bg-surface", className)} aria-labelledby={id && title ? `${id}-title` : undefined}>
      {title ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <h2 id={id ? `${id}-title` : undefined} className="text-md font-semibold">
            {title}
          </h2>
          {actions}
        </div>
      ) : null}
      <div className="p-4">{children}</div>
    </section>
  );
}

/** External link to a public source; always marked with an icon and opened in a new tab. */
export function ExtLink({
  href,
  children,
  className,
  quiet = true,
  label,
}: {
  href: string | null | undefined;
  children: ReactNode;
  className?: string;
  quiet?: boolean;
  label?: string;
}) {
  if (!href) return <span className={className}>{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      className={cx(quiet ? "quiet-link" : "prose-link", "inline-flex items-center gap-1", className)}
    >
      {children}
      <ExternalLink aria-hidden="true" size={12} strokeWidth={1.5} className="shrink-0" />
      <span className="sr-only">(opens GitHub in a new tab)</span>
    </a>
  );
}

export function KepLink({ number, label }: { number: number | null | undefined; label?: string }) {
  if (number === null || number === undefined) return <span className="ident">{label ?? "KEP"}</span>;
  return (
    <Link href={`/explore/kep/${number}` as Route} className="quiet-link ident">
      {label ?? `KEP-${number}`}
    </Link>
  );
}

/** A GitHub login as an identifier, linked to its Person page. */
export function PersonLink({ login, className }: { login: string; className?: string }) {
  return (
    <Link href={`/explore/person/${encodeURIComponent(login)}` as Route} className={cx("quiet-link ident", className)}>
      @{login}
    </Link>
  );
}

/** A SIG as its directory name, linked to its SIG page. */
export function SigLink({ sig, className }: { sig: string; className?: string }) {
  return (
    <Link href={`/explore/sig/${encodeURIComponent(sig)}` as Route} className={cx("quiet-link ident", className)}>
      {sig}
    </Link>
  );
}

export function Login({ login, url }: { login: string; url?: string | null }) {
  return (
    <ExtLink href={url ?? `https://github.com/${login}`} label={`@${login} on GitHub`}>
      <span className="ident">@{login}</span>
    </ExtLink>
  );
}

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const toneClass: Record<Tone, string> = {
  neutral: "bg-surface-subtle text-fg-secondary border-border",
  accent: "bg-accent-subtle text-accent border-transparent",
  success: "bg-success-subtle text-success border-transparent",
  warning: "bg-warning-subtle text-warning border-transparent",
  danger: "bg-danger-subtle text-danger border-transparent",
};

const toneIcon: Record<Exclude<Tone, "neutral">, typeof XCircle> = {
  accent: CircleDot,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};

/** Chip: a coloured tone always carries an icon as well, so colour never conveys meaning alone. */
export function Chip({ tone = "neutral", children, mono }: { tone?: Tone; children: ReactNode; mono?: boolean }) {
  const Icon = tone === "neutral" ? null : toneIcon[tone];
  return (
    <span
      className={cx(
        "inline-flex h-6 items-center gap-1 rounded-sm border px-2 text-sm whitespace-nowrap",
        toneClass[tone],
        mono && "font-mono",
      )}
    >
      {Icon ? <Icon aria-hidden="true" size={14} strokeWidth={1.5} /> : null}
      {children}
    </span>
  );
}

function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "provisional":
      return "warning";
    case "implementable":
      return "accent";
    case "implemented":
      return "success";
    default:
      return "neutral";
  }
}

export function StatusChip({ status }: { status: string | null | undefined }) {
  if (!status) return <Chip>no status</Chip>;
  return <Chip tone={statusTone(status)}>{status}</Chip>;
}

const ERROR_COPY: Record<string, { title: string; hint: string }> = {
  api_unreachable: { title: "The API is not reachable", hint: "The KEP Brain API did not answer. Try again in a moment." },
  timeout: { title: "The request took too long", hint: "Try again; if it keeps happening the graph may be busy." },
  aborted: { title: "Cancelled", hint: "The request was cancelled." },
  not_found: { title: "Not in the graph", hint: "Nothing with that reference is loaded." },
  provider_unavailable: {
    title: "Answering is paused",
    hint: "The language-model provider is unavailable. Audit, Explore and Eval still work.",
  },
  provider_error: { title: "The language model failed", hint: "Try again. Audit, Explore and Eval still work." },
  provider_rate_limited: {
    title: "The language model is rate limited",
    hint: "The provider refused the request after waiting the time it asked for. Try again in a minute; Audit, Explore and Eval still work.",
  },
  budget_exhausted: { title: "Today's question budget is used up", hint: "Tools, Audit, Explore and Eval still work." },
  llm_not_configured: { title: "No language model is configured", hint: "Audit, Explore and Eval work without one." },
  tool_not_found: { title: "Tool not available", hint: "The API does not expose this tool." },
  validation_error: { title: "The API rejected the parameters", hint: "The request did not match the tool's schema." },
  graph_unavailable: { title: "The graph is unavailable", hint: "FalkorDB did not answer. Try again in a moment." },
  graph_timeout: { title: "The graph query timed out", hint: "Try a narrower question or a specific KEP." },
  rate_limited: { title: "Too many requests", hint: "Too many questions from this address; wait a few minutes." },
  capacity_reached: {
    title: "Today's answering budget is used up",
    hint: "Today's answering budget for this deployment is used up. Audit, Explore and Eval still work.",
  },
  question_too_long: { title: "Question too long", hint: "Questions are limited to 1,000 characters." },
  forbidden: { title: "Not allowed", hint: "This action is not available on the public deployment." },
  memory_unavailable: { title: "Memory is unavailable", hint: "Answers continue without recall." },
  ambiguous_reference: { title: "More than one KEP matches", hint: "Pick one of the candidates." },
  bad_response: { title: "Unexpected response", hint: "The API sent something this page cannot read." },
};

/** Inline error where the content would have been. No stack traces, no raw JSON. */
function copyFor(error: ApiFailure): { title: string; hint: string } {
  if (error.code === "rate_limited") {
    if (error.details?.scope === "daily") return ERROR_COPY.capacity_reached;
    const retry = Number(error.details?.retry_after_s);
    if (Number.isFinite(retry) && retry > 0) {
      const minutes = Math.max(1, Math.ceil(retry / 60));
      return {
        title: "Too many requests",
        hint: `Too many questions from this address; try again in ${minutes} minute${minutes === 1 ? "" : "s"}.`,
      };
    }
  }
  return ERROR_COPY[error.code] ?? { title: "The request failed", hint: "Try again in a moment." };
}

export function ErrorState({ error, what, children }: { error: ApiFailure; what?: string; children?: ReactNode }) {
  const copy = copyFor(error);
  return (
    <div role="alert" className="rounded-md border border-danger/40 bg-danger-subtle p-4 text-fg">
      <p className="flex items-center gap-2 font-semibold text-danger">
        <XCircle aria-hidden="true" size={16} strokeWidth={1.5} />
        {what ? `${what}: ` : ""}
        {copy.title}
      </p>
      <p className="mt-1 text-fg-secondary">{copy.hint}</p>
      {error.message && error.code !== "api_unreachable" ? <p className="mt-1 text-sm text-fg-secondary">{error.message}</p> : null}
      <p className="mt-2 text-xs text-fg-muted">
        Code <span className="font-mono">{error.code}</span>
        {error.requestId ? (
          <>
            {" "}· Diagnostic id <span className="font-mono">{error.requestId}</span>
          </>
        ) : null}
      </p>
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-border-strong bg-surface-subtle p-4">
      <p className="font-medium">{title}</p>
      {children ? <div className="mt-1 text-fg-secondary">{children}</div> : null}
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md bg-warning-subtle p-3 text-fg">
      <AlertTriangle aria-hidden="true" size={16} strokeWidth={1.5} className="mt-0.5 shrink-0 text-warning" />
      <div>{children}</div>
    </div>
  );
}

/** Static grey bars in the final layout (no shimmer). */
export function SkeletonBlock({ lines = 3, label = "Loading" }: { lines?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-4" style={{ width: `${90 - ((i * 17) % 40)}%` }} />
      ))}
    </div>
  );
}

export function StatTile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-surface p-4">
      <p className="text-sm text-fg-secondary">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {note ? <p className="mt-1 text-xs text-fg-muted">{note}</p> : null}
    </div>
  );
}

/** Horizontal bar for one count against the largest count in its group; the number is always printed beside it. */
export function MiniBar({ value, max, color = "var(--c-text-muted)" }: { value: number; max: number; color?: string }) {
  const w = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <span aria-hidden="true" className="block h-2 w-full rounded-sm bg-surface-subtle">
      <span className="block h-2 rounded-sm" style={{ width: `${w}%`, background: color }} />
    </span>
  );
}

/** Definition list of facts: label / value pairs. */
export function Facts({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <dt className="text-sm text-fg-secondary">{it.label}</dt>
          <dd className="mt-0.5 break-words">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export const tableClass = "w-full border-collapse text-sm";
export const thClass = "border-b border-border bg-surface-subtle px-3 py-2 text-left font-medium text-fg-secondary whitespace-nowrap";
export const tdClass = "border-b border-border px-3 py-2 align-top";

/** Horizontally scrollable, keyboard-reachable region around a wide table. */
export function TableWrap({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="relative overflow-x-auto" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}

export function Dash() {
  return (
    <span className="text-fg-muted">
      <span aria-hidden="true">—</span>
      <span className="sr-only">none</span>
    </span>
  );
}
