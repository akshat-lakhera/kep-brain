## What changed

## How it was checked

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run pytest -m "not integration"` (api)
- [ ] `pnpm lint && pnpm exec tsc --noEmit && pnpm build` (web)
- [ ] Any fact shown to users still comes from the graph with a source URL

## AI usage disclosure

- [ ] I appended a row to `docs/AI_USAGE.md` that names the concrete human edit or check
- [ ] Any new decision has an ADR in `docs/DECISIONS.md`
