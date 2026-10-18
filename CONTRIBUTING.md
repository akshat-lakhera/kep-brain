# Contributing

The project has a single maintainer, so small, focused changes are easiest to review.

1. Open an issue first for anything larger than a small fix. Use the bug report or UI suggestion template.
2. Run the checks in the README "Development" section before opening a pull request:
   - API (`apps/api`): `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -m "not integration"`
   - Web (`apps/web`): `pnpm lint`, `pnpm exec next typegen`, `pnpm exec tsc --noEmit`, `pnpm build`
3. Any fact shown to users must come from the graph with a source URL.
4. Record new design decisions in `docs/DECISIONS.md`.
5. If AI coding assistants helped, add a row to `docs/AI_USAGE.md` that names the human check.

Report security problems as described in [SECURITY.md](SECURITY.md).
