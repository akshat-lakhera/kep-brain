# Decision log

## ADR-0001 FalkorDB as the only store

- Date: 2026-10-15
- Status: accepted
- Decision: FalkorDB v4.22.0 holds the knowledge graph, the answer cache, per-user memory and operations data (separate graphs: `kep`, `ops`, `mem:<id>`). FastAPI serves the API and Next.js the web app. The data scope is three SIGs: sig-node, sig-scheduling and sig-apps.
- Consequence: one database, one language per tier, and a data set small enough to verify by hand.

## ADR-0002 LLM provider: OpenAI-compatible endpoint

- Date: 2026-10-15
- Status: accepted
- Context: the agent needs a hosted model reachable through a single key.
- Decision: one provider adapter, `openai_compatible`, pointed at Groq's OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`, models `openai/gpt-oss-120b` and cheap tier `openai/gpt-oss-20b`, fallback `qwen/qwen3.8-27b`). The key is `OPENAI_API_KEY`. The free tier is rate-limited, so the client paces requests (`LLM_REQUESTS_PER_MINUTE`), honours Retry-After (up to `LLM_MAX_RETRIES`), and falls back to a second model. Without a key `/v1/ask` answers 503 (`llm_not_configured`).
- Consequence: any OpenAI-compatible endpoint works by changing the base URL, key and model names. Answer quality is measured on the eval set rather than assumed.

## ADR-0003 Single ACL mode for development

- Date: 2026-10-15
- Status: accepted
- Decision: development runs FalkorDB with one password (`FALKORDB_ACL_MODE=single`). The per-role users (reader, memory, ops, writer) stay available as `aclfile` mode and the settings exist for it.
- Consequence: simpler local setup. In `single` mode, read-only enforcement for the query path relies on the application's read-only execution path (`GRAPH.RO_QUERY`), not on database permissions.

## ADR-0004 Evidence-first answers

- Date: 2026-10-15
- Status: accepted
- Decision: the answering agent may call only read-only catalog tools. A deterministic validator checks that every inline citation points to a record returned in the same request and that the answer has at least one; otherwise the answer is replaced by an abstention.
- Consequence: every citation shown to users is a graph node with a public GitHub URL.
