# ADR 0009 · Evidence-first answers: deterministic claim validator, explicit abstention, validated reveal

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Validator rules owned by H-Review (ADR 0026); awaiting ratification at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Thresholds and chunk size yes; the validator, abstention contract and validate-before-reveal no |
| Related | `02-architecture.md` §6.3, §6.4, §12; ADR 0004, ADR 0010, ADR 0024 |

## Context

T03 asks for "Answers with clear sources"; T01 for "Explainable results"; FalkorDB's judge praised "the LLM answering only from rows the graph returned" and "honesty about failures". The eval scores answers against ground truth and includes questions where the right behaviour is to abstain. Structured outputs (`output_config.format`) let us demand a schema; Anthropic citations are not used because our evidence is graph rows and citations are incompatible with structured output (claude-api skill, cached 2026-10-06).

v1 of this design streamed `token` deltas of the answer to the browser while the answer was still unvalidated, and the UI rendered them as they arrived. A validation failure then arrived after the reader (and the screen recording) had already seen the unsupported or injected sentences.

## Decision

- The final model turn returns the `Answer` schema: `answer_markdown`, `claims[] {text, evidence_ids[]}`, `abstained`, `abstain_reason`, `confidence`.
- Evidence ids exist only for rows returned by tools during the same request: `{evidence_id, label, key, title, url}` with `evidence_id = base32(sha1(label + "|" + key))[:12]` and `url` built by code from node properties.
- **Deterministic validator** after the model: every claim cites ≥ 1 evidence id seen in this request; every URL in `answer_markdown` equals an evidence URL; `abstained = false` requires ≥ 1 claim; no claim cites a `Finding`, `Episode` or `Fact` id (memory and findings are context, not evidence; their underlying `kep` rows are resolved and cited instead). A violation turns the answer into an abstention with `abstain_reason = unsupported_claims`; the rejected text never leaves the server (debug log only).
- **Validate, then reveal.** `status`, `tool_call`, `path` and `citation` events stream live (they are graph rows and tool metadata). The final answer is buffered; only after validation are `token` events emitted, chunked from the validated `answer_markdown` (≈ 40 characters per event every 15 ms). An abstained answer emits zero `token` events and one `done {abstained: true, abstain_reason}`. The Ask page shows a `checking` phase in between.
- Abstention reasons: `no_evidence`, `out_of_scope`, `unsupported_claims`, `budget_exhausted`, `graph_unavailable`. Abstentions are HTTP 200 and first-class in the UI.
- Every answer carries `paths` and the freshness block, including open findings about the cited KEPs.
- The freshness agent's verdicts pass the same validator before a finding opens (ADR 0024).

## Alternatives considered

- Streaming tokens and retracting on failure (v1): the retraction arrives after the claim was read and recorded.
- Trusting the model's citations: one fabricated URL in a demo is fatal with judges who click.
- LLM-as-judge for citation checking: non-deterministic and costs tokens; the deterministic check suffices because evidence ids are opaque to the model.
- Not streaming anything: hides the live tool trace, which is the most explanatory part of the experience.

## Consequences

- Time to the first answer character rises by the validation and chunking time only (milliseconds after the final model turn); the tool trace still appears live.
- Contract tests: a recorded transcript whose answer cites an unseen evidence id yields zero `token` events and one `done {abstained: true, abstain_reason: "unsupported_claims"}`; a valid transcript's concatenated `token` text equals the validated `answer_markdown`.
- Some correct answers are downgraded when the model forgets an evidence id; the eval tracks the downgrade rate.

## Revision 2026-10-12

Validate-before-reveal streaming; findings and memory excluded as evidence; validator owned by a named human; the freshness agent uses the same validator (design review R2, R4, R11).
