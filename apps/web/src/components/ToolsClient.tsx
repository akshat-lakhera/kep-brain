"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { clientApi } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/core";
import type { ToolResult, ToolSpec } from "@/lib/api/types";
import { buildParams, fieldsOf, initialValues, type Field, type FieldValue } from "@/lib/schema";
import { ToolResultView } from "./ToolResultView";
import { EmptyState, ErrorState, cx } from "./ui";

type Run =
  | { kind: "idle" }
  | { kind: "loading"; params: Record<string, unknown> }
  | { kind: "error"; params: Record<string, unknown>; error: ApiFailure }
  | { kind: "done"; params: Record<string, unknown>; result: ToolResult };

const control = "h-8 w-full rounded-sm border border-border-input bg-surface px-2 text-base";

/** Tool console: the list from GET /v1/tools on the left, a form built from params_schema and the result on the right. */
export function ToolsClient({ tools }: { tools: ToolSpec[] }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const wanted = params.get("tool");
  const selected = tools.find((t) => t.name === wanted) ?? tools[0];

  function select(name: string) {
    router.replace(`${pathname}?tool=${encodeURIComponent(name)}` as Route, { scroll: false });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-12">
      <nav aria-label="Tools" className="lg:col-span-3">
        <label className="flex flex-col gap-1 text-sm text-fg-secondary lg:hidden">
          Tool
          <select value={selected.name} onChange={(e) => select(e.target.value)} className={control}>
            {tools.map((t) => (
              <option key={t.name} value={t.name}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <ul className="hidden divide-y divide-border rounded-md border border-border bg-surface lg:block">
          {tools.map((t) => {
            const active = t.name === selected.name;
            return (
              <li key={t.name}>
                <button
                  type="button"
                  aria-current={active ? "true" : undefined}
                  onClick={() => select(t.name)}
                  className={cx(
                    "block w-full px-3 py-2 text-left",
                    active ? "bg-accent-subtle text-fg" : "text-fg-secondary hover:bg-surface-subtle hover:text-fg",
                  )}
                >
                  <span className={cx("font-mono text-sm", active && "font-medium")}>{t.name}</span>
                  <span className="mt-0.5 line-clamp-2 block text-xs text-fg-muted">{t.description}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="min-w-0 lg:col-span-9">
        <ToolPanel key={selected.name} tool={selected} />
      </div>
    </div>
  );
}

function ToolPanel({ tool }: { tool: ToolSpec }) {
  const base = useId();
  const fields = useMemo(() => fieldsOf(tool.params_schema), [tool]);
  const [values, setValues] = useState<Record<string, FieldValue>>(() => initialValues(fields));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [run, setRun] = useState<Run>({ kind: "idle" });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  function set(name: string, v: FieldValue) {
    setValues((prev) => ({ ...prev, [name]: v }));
    setErrors((prev) => {
      if (!(name in prev)) return prev;
      const next = { ...prev };
      delete next[name];
      return next;
    });
  }

  async function submit() {
    const built = buildParams(fields, values);
    setErrors(built.errors);
    if (Object.keys(built.errors).length > 0) {
      const first = fields.find((f) => f.name in built.errors);
      if (first) document.getElementById(`${base}-${first.name}`)?.focus();
      return;
    }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRun({ kind: "loading", params: built.params });
    const res = await clientApi.runTool(tool.name, built.params, ctrl.signal);
    if (ctrl.signal.aborted) return;
    setRun(res.ok ? { kind: "done", params: built.params, result: res.data } : { kind: "error", params: built.params, error: res.error });
  }

  const loading = run.kind === "loading";
  const required = fields.filter((f) => f.required).length;

  return (
    <div className="space-y-6">
      <section aria-labelledby={`${base}-title`} className="rounded-md border border-border bg-surface">
        <div className="border-b border-border px-4 py-3">
          <h2 id={`${base}-title`} className="font-mono text-md font-semibold">
            {tool.name}
          </h2>
          <p className="mt-1 max-w-[80ch] text-fg-secondary">{tool.description}</p>
        </div>
        <form
          className="space-y-4 p-4"
          aria-busy={loading}
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {fields.length === 0 ? (
            <p className="text-sm text-fg-secondary">This tool takes no parameters.</p>
          ) : (
            <>
              <p className="text-xs text-fg-muted">
                {required === 0 ? "Every parameter is optional; empty fields take the API's defaults." : `${required} required parameter${required === 1 ? "" : "s"}; empty optional fields take the API's defaults.`}
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                {fields.map((f) => (
                  <FieldControl key={f.name} id={`${base}-${f.name}`} field={f} value={values[f.name]} error={errors[f.name]} onChange={(v) => set(f.name, v)} />
                ))}
              </div>
            </>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={loading} className="h-8 rounded-sm bg-accent px-4 text-base font-medium text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50">
              Run
            </button>
            {loading ? (
              <button
                type="button"
                onClick={() => {
                  abortRef.current?.abort();
                  abortRef.current = null;
                  setRun({ kind: "idle" });
                }}
                className="h-8 rounded-sm border border-border-input px-3 text-base"
              >
                Cancel
              </button>
            ) : null}
            <span className="text-xs text-fg-muted">
              Runs <span className="font-mono">POST /v1/tools/{tool.name}</span> as a read-only Cypher query. No language model is involved.
            </span>
          </div>
        </form>
      </section>

      <section aria-label="Result" aria-live="polite">
        {run.kind === "idle" ? (
          <EmptyState title="Not run yet">The rows, evidence links, traversed paths and the Cypher template appear here after Run.</EmptyState>
        ) : null}
        {run.kind === "loading" ? (
          <div role="status" className="space-y-2">
            <span className="sr-only">Running {tool.name}</span>
            <div className="skeleton h-4 w-8/12" />
            <div className="skeleton h-40 w-full" />
          </div>
        ) : null}
        {run.kind === "error" ? (
          <ErrorState error={run.error} what={tool.name}>
            <ValidationDetails details={run.error.details} />
          </ErrorState>
        ) : null}
        {run.kind === "done" ? <ToolResultView name={tool.name} params={run.params} result={run.result} /> : null}
      </section>
    </div>
  );
}

/** The API's validation_error lists the offending fields and messages under details. */
function ValidationDetails({ details }: { details: Record<string, unknown> | null }) {
  if (!details) return null;
  const errors = Array.isArray(details.errors) ? details.errors.filter((e): e is string => typeof e === "string") : [];
  const fields = Array.isArray(details.fields) ? details.fields.filter((e): e is string => typeof e === "string") : [];
  if (errors.length === 0 && fields.length === 0) return null;
  return (
    <div className="text-sm">
      {fields.length ? (
        <p>
          Fields: <span className="font-mono">{fields.join(", ")}</span>
        </p>
      ) : null}
      {errors.length ? (
        <ul className="mt-1 list-disc pl-5">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function FieldControl({
  id,
  field: f,
  value,
  error,
  onChange,
}: {
  id: string;
  field: Field;
  value: FieldValue | undefined;
  error: string | undefined;
  onChange: (v: FieldValue) => void;
}) {
  const text = typeof value === "string" ? value : "";
  const list = Array.isArray(value) ? value : [];
  const describe = [f.description ? `${id}-d` : null, error ? `${id}-e` : null].filter(Boolean).join(" ") || undefined;
  const wide = f.kind === "enum-list" || f.kind === "json";
  const hint = [
    f.required ? "required" : "optional",
    f.defaultValue !== undefined && f.defaultValue !== null && f.kind !== "enum-list" ? `default ${JSON.stringify(f.defaultValue)}` : null,
    f.kind === "text-list" ? `comma-separated${f.maxItems !== null ? `, at most ${f.maxItems}` : ""}` : null,
    f.kind === "integer" || f.kind === "number"
      ? [f.minimum !== null ? `min ${f.minimum}` : null, f.maximum !== null ? `max ${f.maximum}` : null].filter(Boolean).join(", ") || null
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  let input: React.ReactNode;
  switch (f.kind) {
    case "enum":
      input = (
        <select id={id} value={text} onChange={(e) => onChange(e.target.value)} aria-describedby={describe} aria-invalid={Boolean(error)} className={control}>
          {!f.required || text === "" ? <option value="">{f.required ? "Pick a value" : "Not set"}</option> : null}
          {f.options.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
      );
      break;
    case "boolean":
      input = (
        <select id={id} value={text} onChange={(e) => onChange(e.target.value)} aria-describedby={describe} aria-invalid={Boolean(error)} className={control}>
          {!f.required ? <option value="">Not set</option> : null}
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
      break;
    case "enum-list":
      input = (
        <fieldset id={id} aria-labelledby={`${id}-l`} aria-describedby={describe} className="flex flex-wrap gap-x-4 gap-y-1">
          {f.options.map((o) => {
            const v = String(o);
            const checked = list.includes(v);
            return (
              <label key={v} className="inline-flex min-h-6 items-center gap-1 font-mono text-sm">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => onChange(e.target.checked ? [...list, v] : list.filter((x) => x !== v))}
                  className="h-4 w-4 accent-accent"
                />
                {v}
              </label>
            );
          })}
        </fieldset>
      );
      break;
    case "integer":
    case "number":
      input = (
        <input
          id={id}
          type="number"
          inputMode={f.kind === "integer" ? "numeric" : "decimal"}
          step={f.kind === "integer" ? 1 : "any"}
          min={f.minimum ?? undefined}
          max={f.maximum ?? undefined}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={describe}
          aria-invalid={Boolean(error)}
          className={cx(control, "font-mono")}
        />
      );
      break;
    case "json":
      input = (
        <textarea
          id={id}
          rows={3}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={describe}
          aria-invalid={Boolean(error)}
          placeholder="JSON"
          className="block w-full rounded-sm border border-border-input bg-surface p-2 font-mono text-sm"
        />
      );
      break;
    default:
      input = (
        <input
          id={id}
          type="text"
          value={text}
          onChange={(e) => onChange(e.target.value)}
          maxLength={f.maxLength ?? undefined}
          aria-describedby={describe}
          aria-invalid={Boolean(error)}
          autoComplete="off"
          className={cx(control, "font-mono")}
        />
      );
  }

  return (
    <div className={cx("min-w-0", wide && "sm:col-span-2")}>
      {f.kind === "enum-list" ? (
        <span id={`${id}-l`} className="block text-sm">
          <span className="font-mono">{f.name}</span> <span className="text-xs text-fg-muted">{hint}</span>
        </span>
      ) : (
        <label htmlFor={id} className="block text-sm">
          <span className="font-mono">{f.name}</span> <span className="text-xs text-fg-muted">{hint}</span>
        </label>
      )}
      <div className="mt-1">{input}</div>
      {f.description ? (
        <p id={`${id}-d`} className="mt-1 text-xs text-fg-secondary">
          {f.description}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-e`} role="alert" className="mt-1 text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
