# Decision log

Decisions made during the event. Design-phase ADRs are in `docs/design/adr/`.

## ADR-0001 Pre-event notes and the archived template

- Date: 2026-10-15
- Status: accepted
- Context: the event rules allow notes, sketches and diagrams before the start, but main coding must begin after it. A generic FastAPI, Next.js and FalkorDB template was prepared on 2026-10-11 and 2026-10-12, which is close to scaffolding.
- Decision: the design notes (written 2026-10-11 to 2026-10-14) are committed as a separate first commit, "Pre-event notes", containing `docs/` only. The template was archived outside the repository, was not used and was not read during the event. Code starts after 2026-10-15 00:01 IST; the scaffold comes from `uv init` and `create-next-app`, and the rest is written afterwards. `git log` shows the boundary.
- Consequence: about three hours of rebuilding, in exchange for a clean provenance statement (README, "Provenance").

## ADR-0002 Decisions fixed by the team lead

- Date: 2026-10-15
- Status: accepted
- Decision: FalkorDB v4.22.0 as the only store; FastAPI for the API and Next.js for the web app; scope of three SIGs (sig-node, sig-scheduling, sig-apps); Track 3 (Company Brain) is the master track, with Track 1 and Track 2 as layers.
- Consequence: one graph, one language per tier, and a data set small enough to verify by hand.

## ADR-0003 LLM provider: OpenAI-compatible, pointed at Groq

- Date: 2026-10-15
- Status: accepted
- Context: the design prefers a hosted Claude model, but the team has no Anthropic API key. A Groq key is available.
- Decision: the provider adapter supports `anthropic` and `openai_compatible`. The default is `openai_compatible` against Groq's OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`, models `openai/gpt-oss-120b` and cheap tier `openai/gpt-oss-20b`, fallback `qwen/qwen3.8-27b`). The key is `OPENAI_API_KEY`. The free tier is rate-limited, so the client paces requests (`LLM_REQUESTS_PER_MINUTE`), honours Retry-After (up to `LLM_MAX_RETRIES`), and falls back to a second model. The Anthropic adapter remains available by setting `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.
- Consequence: switching provider is configuration only. Answer quality is measured on the eval set rather than assumed.

## ADR-0004 Single ACL mode for development

- Date: 2026-10-15
- Status: accepted
- Decision: development runs FalkorDB with one password (`FALKORDB_ACL_MODE=single`). The per-role users (reader, memory, ops, writer) stay available as `aclfile` mode and the settings exist for it.
- Consequence: simpler local setup. In `single` mode, read-only enforcement for the query path relies on the application's read-only execution path, not on database permissions.
