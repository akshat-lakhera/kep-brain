// Types mirroring the KEP Brain HTTP API (/v1). Field names follow the API exactly.

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    request_id?: string | null;
    details?: Record<string, unknown> | null;
  };
}

export interface Meta {
  graph: { nodes: number; edges: number; keps: number; findings: number; people: number };
  sources: {
    enhancements_sha: string | null;
    community_sha: string | null;
    tickets_as_of: string | null;
  };
  sigs: string[];
  llm: { provider: string | null; model: string | null; configured: boolean };
  falkordb_image: string | null;
}

export interface KepCard {
  key: string;
  number: number | null;
  title: string;
  owning_sig: string | null;
  status: string | null;
  stage: string | null;
  latest_milestone: string | null;
  url: string;
  open_findings: number;
}

export interface KepList {
  items: KepCard[];
}

export interface PersonRef {
  login: string;
  url: string;
}

export interface KepRef {
  key: string;
  number: number | null;
  title: string | null;
  status: string | null;
  url: string;
  declared_by?: string | null;
}

export interface TrackingIssue {
  key: string;
  number: number;
  state: string;
  state_reason: string | null;
  closed_at_iso: string | null;
  labels: string[];
  milestone: string | null;
  url: string;
}

export interface Finding {
  key: string;
  kind: string;
  kep_path: string;
  kep_number: number | null;
  kep_title: string | null;
  owning_sig: string | null;
  state: string;
  a_label: string;
  a_value: string | null;
  a_url: string | null;
  b_label: string;
  b_value: string | null;
  b_url: string | null;
  suggested_fix: string | null;
  detected_at_iso: string | null;
  triage_verdict: string | null;
  assessment: string | null;
}

export interface Evidence {
  evidence_id: string;
  label: string;
  key: string;
  title: string | null;
  url: string | null;
}

export interface KepMilestones {
  alpha: string | null;
  beta: string | null;
  stable: string | null;
  deprecated: string | null;
  disabled: string | null;
  removed: string | null;
}

export interface KepDetail extends KepCard {
  summary: string | null;
  sig_dir: string | null;
  creation_date: string | null;
  last_updated: string | null;
  milestones: KepMilestones;
  authors: PersonRef[];
  reviewers: PersonRef[];
  approvers: PersonRef[];
  prr_approvers: { login: string; stage: string | null; url: string }[];
  feature_gates: string[];
  participating_sigs: string[];
  tracking_issue: TrackingIssue | null;
  relations: { replaces: KepRef[]; replaced_by: KepRef[]; see_also: KepRef[] };
  findings: Finding[];
  sections: { anchor: string; heading: string; kind: string | null; url: string }[];
  source_url: string;
}

export interface StatusChangeOut {
  key: string;
  kind: string;
  field: string;
  op: string | null;
  from_value: string | null;
  to_value: string | null;
  at_iso: string | null;
  actor_login: string | null;
  is_reversal: boolean;
  source_url: string | null;
  commit_sha: string | null;
  pr: { number: number; url: string } | null;
}

export interface DecisionOut {
  key: string;
  kind: string;
  summary: string | null;
  decided_at_iso: string | null;
  human_decider: boolean;
  deciders: { login: string; role: string; url: string }[];
  evidence: Evidence[];
}

export interface ItemList<T> {
  items: T[];
}

export interface FindingsSummary {
  flagged_keps: number;
  total: number;
  by_kind: Record<string, number>;
  by_sig: Record<string, number>;
}

export interface FindingsResponse {
  summary: FindingsSummary;
  items: Finding[];
}

export interface GraphNode {
  id: string;
  label: string;
  key: string;
  title: string | null;
  url: string | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface GraphOut {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Citation {
  index: number;
  evidence_id: string;
  label: string;
  key: string;
  title: string | null;
  url: string | null;
}

export interface ToolCallOut {
  step: number;
  name: string;
  params: Record<string, unknown>;
  ms: number;
  rows: number;
  truncated: boolean;
  error?: string | null;
}

export interface AskResponse {
  request_id: string;
  question: string;
  answer_markdown: string;
  citations: Citation[];
  tool_calls: ToolCallOut[];
  graph: GraphOut;
  abstained: boolean;
  abstain_reason?: string | null;
  latency_ms: number;
  model: string | null;
  findings_recalled: string[];
  memory: { recalled: string[]; remembered: string[] };
}

/** One finding with the evidence records it was derived from (GET /v1/findings/{key}). */
export interface FindingDetail extends Finding {
  evidence: Evidence[];
}

/** POST /v1/tools/{name} (06 C2). */
export interface ToolResult {
  rows: Record<string, unknown>[];
  evidence: Evidence[];
  paths: string[][];
  truncated: boolean;
  ms: number;
  template: string;
}

/** First row of the `draft_stale_doc_issue` tool: a draft composed by code, never posted. */
export interface IssueDraft {
  finding_key: string;
  title: string;
  body: string;
  target_repo: string;
  status: string;
  posted: boolean;
  evidence_keys: string[];
}

// Server-sent events of POST /v1/ask/stream (06 C3s), in the order they may arrive.

export interface SseStatus {
  phase: string;
  label: string;
  wait_s?: number;
}

/** `tool_call` carries the read-only Cypher template as well as the fields of ToolCallOut. */
export interface SseToolCall extends ToolCallOut {
  template?: string;
}

export interface SsePath extends GraphOut {
  path_node_ids?: string[];
  truncated?: boolean;
}

/** Evidence as it is read; `index` is present only for the numbered citations of the final answer. */
export interface SseCitation {
  index?: number;
  evidence_id: string;
  source_type: string;
  title: string | null;
  locator: string;
  url: string | null;
  excerpt?: string | null;
}

export interface SseToken {
  text: string;
}

export interface SseMemory {
  recalled: string[];
  remembered: string[];
  findings_recalled: string[];
}

export interface SseDone {
  request_id: string;
  nodes_read: number;
  sources: number;
  latency_ms: number;
  abstained: boolean;
  abstain_reason?: string | null;
}

export interface SseError {
  code: string;
  message: string;
  request_id?: string | null;
}

export type AskEvent =
  | { event: "status"; data: SseStatus }
  | { event: "tool_call"; data: SseToolCall }
  | { event: "path"; data: SsePath }
  | { event: "citation"; data: SseCitation }
  | { event: "token"; data: SseToken }
  | { event: "memory"; data: SseMemory }
  | { event: "done"; data: SseDone }
  | { event: "error"; data: SseError };

export interface EvalQuestion {
  id: string;
  kind?: string | null;
  text: string;
  judge_order?: number | null;
}

/** One arm's result in an eval summary (04 §7, §8.2). Accuracy is a fraction 0..1. */
export interface EvalArm {
  arm: string;
  name?: string | null;
  n?: number;
  correct?: number;
  accuracy?: number;
  ci?: [number, number] | null;
  abstained?: number;
  errored?: number;
  p50_ms?: number;
  p95_ms?: number;
  [extra: string]: unknown;
}

export interface EvalArmNotRun {
  arm: string;
  reason: string;
}

/**
 * `evals/runs/<utc>/summary.json` as served by GET /v1/eval/latest (`run` is the directory name the API adds).
 * The runner is not built yet; the page reads these fields and shows anything else generically.
 */
export interface EvalRun {
  run?: string;
  run_id?: string;
  created_at?: string;
  started_at?: string;
  commit?: string | null;
  questions?: number;
  reps?: number;
  model?: string | null;
  judge_model?: string | null;
  arms?: EvalArm[] | Record<string, EvalArm | number> | string[];
  arms_not_run?: EvalArmNotRun[] | Record<string, string>;
  by_kind?: Record<string, Record<string, unknown>>;
  paired_difference?: { baseline?: string; diff?: number; ci?: [number, number] } | null;
  noise_floor?: string | null;
  per_question?: Record<string, unknown>[];
  audit_precision?: Record<string, unknown> | null;
  memory?: Record<string, unknown> | null;
  latency_by_stage?: Record<string, unknown> | null;
  load_test?: Record<string, unknown> | null;
  baseline?: Record<string, unknown> | null;
  [extra: string]: unknown;
}

/** Per-user memory (02 §12); sub-collections are rendered generically. */
export interface MemoryMe {
  memory_id?: string;
  sessions?: Record<string, unknown>[];
  recent_episodes?: Record<string, unknown>[];
  facts?: Record<string, unknown>[];
  procedures?: Record<string, unknown>[];
  [extra: string]: unknown;
}

export interface AgentsBoard {
  agents?: {
    name: string;
    kind?: string;
    status?: string;
    current_task?: string | null;
    last_seen_at?: string | null;
  }[];
  handoffs_last_hour?: Record<string, unknown>[];
  tasks?: Record<string, unknown>[];
  findings_recent?: Record<string, unknown>[];
  [extra: string]: unknown;
}
