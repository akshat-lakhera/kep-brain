# ADR 0010 · LLM provider adapter: Anthropic default, OpenAI-compatible fallback

Amended 2026-10-12 per 06 §1.6 (ratified register).

| | |
|---|---|
| Status | Proposed (AI-drafted 2026-10-11, revised 2026-10-12). Provider shape fixed by the team; model roles awaiting ratification by H-Lead at HUM-00d |
| Date | 2026-10-11; revised 2026-10-12 |
| Veto-able | Model ids yes (`claude-opus-5-5` is the documented planner alternative) |
| Related | `02-architecture.md` §6.1, §10.1, §11.1; `06-build-plan.md` B2, B6; ADR 0009, ADR 0024 |

## Context

The team fixed: a provider adapter, Anthropic as default with `claude-sonnet-5-5` for planning and answering and `claude-haiku-5-5` for cheap work, an OpenAI-compatible fallback, provider chosen by env. From the claude-api skill (cached 2026-10-06; re-verify at docs.anthropic.com on 2026-10-15): `claude-sonnet-5-5` $2/$10 per MTok, adaptive thinking on by default, `tool_choice` `any`/`tool` return 400, `output_config.format` for structured outputs, `strict: true` tools, prompt caching by prefix, `fallbacks: "default"` with beta header `server-side-fallback-2026-07-01`, `stop_reason: "refusal"` must be checked; `claude-haiku-5-5` $0.10/$0.50 per MTok. SDK versions (PyPI, 2026-10-12): `anthropic` 1.13.0, `openai` 3.29.0, `voyageai` 0.5.0.

## Decision

- `app.agent.provider` defines one interface, `complete(messages, tools, output_schema, model, max_tokens, effort)`, returning content blocks, tool uses, the parsed structured output, `stop_reason` and usage. Implementations: `AnthropicProvider` (Messages API) and `OpenAICompatibleProvider` (Chat Completions with `base_url`), selected by `LLM_PROVIDER` (unprefixed settings, B2).
- Roles: `LLM_MODEL` (planner, default `claude-sonnet-5-5`): planning, tool selection and the final structured answer of the Q&A agent. `LLM_MODEL_CHEAP` (default `claude-haiku-5-5`): scope classification, entity extraction, memory fact extraction, and the **freshness agent's verifier** (ADR 0024).
- Anthropic specifics: adaptive thinking; `strict: true` tools; `tool_choice: auto` with the first tool named in the system prompt; structured final answer via `output_config.format`, **not streamed to the browser** (ADR 0009); `fallbacks: "default"` + beta header; one cache breakpoint after the static prefix; `stop_reason` checked before `content`.
- Errors map to `provider_error` (502) or `provider_rate_limited` (503 with `Retry-After`).
- Embeddings (only for the vector baseline arm and the deferred `search_sections`): dimension **1024**, cosine (B6): `voyage-4` on the Anthropic path (`VOYAGE_API_KEY`), `text-embedding-3-small` with `dimensions: 1024` on the OpenAI-compatible path; enabled by `EMBEDDINGS_ENABLED`.
- Spend: `LLM_DAILY_BUDGET_USD` (5) for public asks and `FINDINGS_AGENT_DAILY_USD` (1.00) for the freshness agent, both counted in `ops` `BudgetDay`.

## Alternatives considered

- `claude-opus-5-5` as planner: higher quality at twice Sonnet's price; a one-line env change.
- LangChain or LlamaIndex abstraction: more code paths than two providers need, and hides request shapes the team must explain.
- OpenAI-compatible path only: loses structured output, strict tools and server-side fallbacks that the answer contract relies on.

## Consequences

- ≈ $0.02–0.06 per answer; ≈ $0.0005 per verified finding.
- CI replays recorded provider responses, so tests are deterministic and free; the `openai_compatible` adapter is smoke-tested against a real endpoint before CP6 when a key exists (B22).

> **Superseded content (v1 of this ADR).** v1 used the settings prefix `KEPBRAIN_` and an embedding dimension of 1536; both are replaced as above (B2, B6).

## Revision 2026-10-12

Unprefixed settings; 1024-dimension embeddings with named models; the freshness agent added as a Haiku role; answers not streamed from the provider to the browser (design review R4, R7, R11).
