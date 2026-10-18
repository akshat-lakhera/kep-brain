# KEP Brain API

The Python service of KEP Brain: the FastAPI `/v1` routes, the ingest worker (`python -m app.worker`), the
answering agent with its claim validator, the per-user memory graphs and the MCP server (`python -m app.mcp`).
Everything reads and writes one FalkorDB instance; the request path reads the `kep` graph with `GRAPH.RO_QUERY`.

Run the checks from this directory with [uv](https://docs.astral.sh/uv/): `uv sync`, then `uv run ruff check .`,
`uv run ruff format --check .` and `uv run pytest -m "not integration"`. Integration tests write throwaway
graphs on a running FalkorDB (`FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD` in the environment or the
repo-root `.env`): `uv run pytest -m integration -q`. The repository README has the full setup and the
configuration table.
