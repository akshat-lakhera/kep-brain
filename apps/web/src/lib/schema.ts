import type { JsonSchema } from "./api/types";
import { humanize } from "./format";

export type FieldKind = "text" | "integer" | "number" | "boolean" | "enum" | "enum-list" | "text-list" | "json";

/** One form control derived from a tool's params_schema. */
export interface Field {
  name: string;
  label: string;
  description: string | null;
  required: boolean;
  kind: FieldKind;
  options: (string | number)[];
  defaultValue: unknown;
  minimum: number | null;
  maximum: number | null;
  minLength: number | null;
  maxLength: number | null;
  maxItems: number | null;
  pattern: string | null;
}

/** Form state: lists of enum choices as arrays, everything else as the typed string. */
export type FieldValue = string | string[];

/** Unwrap `anyOf: [X, {type: null}]` (pydantic's Optional) to X, keeping the outer description and default. */
function effective(s: JsonSchema): JsonSchema {
  if (!Array.isArray(s.anyOf)) return s;
  const branch = s.anyOf.find((b) => b.type !== "null") ?? s.anyOf[0];
  return { ...branch, description: s.description ?? branch.description, title: s.title ?? branch.title, default: s.default ?? branch.default };
}

function isNullable(s: JsonSchema): boolean {
  return Array.isArray(s.anyOf) && s.anyOf.some((b) => b.type === "null");
}

function scalarOptions(e: unknown[] | undefined): (string | number)[] {
  return (e ?? []).filter((x): x is string | number => typeof x === "string" || typeof x === "number");
}

function kindOf(s: JsonSchema): { kind: FieldKind; options: (string | number)[] } {
  const type = Array.isArray(s.type) ? s.type.find((t) => t !== "null") : s.type;
  if (Array.isArray(s.enum) && s.enum.length > 0) return { kind: "enum", options: scalarOptions(s.enum) };
  if (type === "array") {
    const items = s.items ? effective(s.items) : {};
    if (Array.isArray(items.enum) && items.enum.length > 0) return { kind: "enum-list", options: scalarOptions(items.enum) };
    if (items.type === "string" || items.type === undefined) return { kind: "text-list", options: [] };
    return { kind: "json", options: [] };
  }
  if (type === "boolean") return { kind: "boolean", options: [] };
  if (type === "integer") return { kind: "integer", options: [] };
  if (type === "number") return { kind: "number", options: [] };
  if (type === "string") return { kind: "text", options: [] };
  return { kind: "json", options: [] };
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** The ordered fields of an object schema. Optional means: not required, nullable, or carrying a default. */
export function fieldsOf(schema: JsonSchema): Field[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, raw]) => {
    const s = effective(raw);
    const { kind, options } = kindOf(s);
    return {
      name,
      label: humanize(name),
      description: typeof s.description === "string" ? s.description : null,
      required: required.has(name) && !isNullable(raw) && raw.default === undefined,
      kind,
      options,
      defaultValue: raw.default,
      minimum: num(s.minimum),
      maximum: num(s.maximum),
      minLength: num(s.minLength),
      maxLength: num(s.maxLength),
      maxItems: num(s.maxItems),
      pattern: typeof s.pattern === "string" ? s.pattern : null,
    };
  });
}

/** Form state with the schema defaults filled in. */
export function initialValues(fields: Field[]): Record<string, FieldValue> {
  const out: Record<string, FieldValue> = {};
  for (const f of fields) {
    const d = f.defaultValue;
    if (f.kind === "enum-list") out[f.name] = Array.isArray(d) ? d.map(String) : [];
    else if (f.kind === "text-list") out[f.name] = Array.isArray(d) ? d.map(String).join(", ") : "";
    else if (f.kind === "json") out[f.name] = d === undefined || d === null ? "" : JSON.stringify(d);
    else out[f.name] = d === undefined || d === null ? "" : String(d);
  }
  return out;
}

function option(f: Field, v: string): string | number | undefined {
  return f.options.find((o) => String(o) === v);
}

/**
 * Turn form state into the request body. Empty fields are omitted so the API applies its own defaults;
 * every problem the browser can see before sending is returned per field.
 */
export function buildParams(fields: Field[], values: Record<string, FieldValue>): { params: Record<string, unknown>; errors: Record<string, string> } {
  const params: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const f of fields) {
    const v = values[f.name];
    const text = typeof v === "string" ? v.trim() : "";
    const list = Array.isArray(v) ? v : [];
    const empty = f.kind === "enum-list" ? list.length === 0 : text === "";
    if (empty) {
      if (f.required) errors[f.name] = `${f.label} is required.`;
      continue;
    }
    switch (f.kind) {
      case "text": {
        if (f.minLength !== null && text.length < f.minLength) errors[f.name] = `At least ${f.minLength} characters.`;
        else if (f.maxLength !== null && text.length > f.maxLength) errors[f.name] = `At most ${f.maxLength} characters.`;
        else if (f.pattern !== null && !new RegExp(f.pattern).test(text)) errors[f.name] = `Must match ${f.pattern}`;
        else params[f.name] = text;
        break;
      }
      case "integer":
      case "number": {
        const n = Number(text);
        if (!Number.isFinite(n)) errors[f.name] = "Must be a number.";
        else if (f.kind === "integer" && !Number.isInteger(n)) errors[f.name] = "Must be a whole number.";
        else if (f.minimum !== null && n < f.minimum) errors[f.name] = `At least ${f.minimum}.`;
        else if (f.maximum !== null && n > f.maximum) errors[f.name] = `At most ${f.maximum}.`;
        else params[f.name] = n;
        break;
      }
      case "boolean":
        params[f.name] = text === "true";
        break;
      case "enum": {
        const o = option(f, text);
        if (o === undefined) errors[f.name] = "Pick one of the listed values.";
        else params[f.name] = o;
        break;
      }
      case "enum-list": {
        const picked = list.map((x) => option(f, x)).filter((x): x is string | number => x !== undefined);
        if (f.maxItems !== null && picked.length > f.maxItems) errors[f.name] = `At most ${f.maxItems} values.`;
        else params[f.name] = picked;
        break;
      }
      case "text-list": {
        const items = text
          .split(/[,\n]/)
          .map((x) => x.trim())
          .filter(Boolean);
        if (f.maxItems !== null && items.length > f.maxItems) errors[f.name] = `At most ${f.maxItems} values.`;
        else params[f.name] = items;
        break;
      }
      case "json": {
        try {
          params[f.name] = JSON.parse(text);
        } catch {
          errors[f.name] = "Must be valid JSON.";
        }
        break;
      }
    }
  }
  return { params, errors };
}
