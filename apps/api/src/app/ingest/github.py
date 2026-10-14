"""Small GitHub GraphQL client for the ticket layer (02 §9.3, 03 §4.5).

- Token: `GITHUB_TOKEN` from settings, else `gh auth token`.
- Retries with backoff on secondary rate limits, abuse detection, 5xx and
  GraphQL `RATE_LIMITED` errors; waits for the primary limit to reset when
  it is exhausted.
- Optional on-disk JSON cache keyed by the query and its variables, so a
  re-run does not re-fetch (`record`: read if present, else fetch and store;
  `replay`: cache only; `off`: always fetch).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
import structlog

from app.settings import Settings

log = structlog.get_logger(__name__)

GRAPHQL_URL = "https://api.github.com/graphql"
CacheMode = Literal["off", "record", "replay"]
MAX_ATTEMPTS = 7
MAX_SLEEP_SECONDS = 900.0


class GitHubError(RuntimeError):
    """A GitHub request failed after retries, or returned no data."""


def resolve_token(settings: Settings) -> str:
    if settings.github_token is not None:
        return settings.github_token.get_secret_value()
    gh = shutil.which("gh")
    if gh is None:
        raise GitHubError("no GITHUB_TOKEN configured and the gh CLI is not installed")
    try:
        out = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=20, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise GitHubError("gh auth token failed") from exc
    token = out.stdout.strip()
    if not token:
        raise GitHubError("gh auth token returned an empty token")
    return token


def default_cache_mode(settings: Settings) -> CacheMode:
    return "record" if settings.env in ("dev", "test") else "off"


def default_cache_dir(settings: Settings) -> Path:
    return Path(settings.repo_cache_dir) / "github"


def _is_secondary_limit(status: int, text: str) -> bool:
    lowered = text.lower()
    return status in (403, 429) and ("secondary rate limit" in lowered or "abuse" in lowered or status == 429)


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        cache_dir: Path | None = None,
        cache_mode: CacheMode = "off",
        timeout_seconds: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if cache_mode != "off" and cache_dir is None:
            raise ValueError("a cache directory is required unless cache_mode is 'off'")
        self._cache_dir = cache_dir
        self._cache_mode = cache_mode
        self._sleep = sleep
        self._http = httpx.Client(
            headers={
                "Authorization": f"bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "kep-brain-worker",
            },
            timeout=timeout_seconds,
            transport=transport,
        )
        self.requests_made = 0
        self.cache_hits = 0

    @classmethod
    def from_settings(cls, settings: Settings, cache_mode: CacheMode | None = None) -> GitHubClient:
        mode = cache_mode or default_cache_mode(settings)
        token = "" if mode == "replay" else resolve_token(settings)
        return cls(token, cache_dir=default_cache_dir(settings), cache_mode=mode)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- cache -----------------------------------------------------------------

    def _cache_path(self, query: str, variables: dict[str, Any]) -> Path | None:
        if self._cache_dir is None or self._cache_mode == "off":
            return None
        canonical = json.dumps({"q": " ".join(query.split()), "v": variables}, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return self._cache_dir / digest[:2] / f"{digest}.json"

    def _cache_read(self, path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    def _cache_write(self, path: Path | None, variables: dict[str, Any], data: dict[str, Any]) -> None:
        if path is None or self._cache_mode != "record":
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.stem}.{uuid.uuid4().hex}.tmp")
        payload = {"fetched_at": datetime.now(UTC).isoformat(), "variables": variables, "data": data}
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        for attempt in range(5):
            try:
                tmp.replace(path)
                return
            except PermissionError:  # Windows: another reader/indexer holds the target briefly
                self._sleep(0.2 * (attempt + 1))
        tmp.unlink(missing_ok=True)
        log.warning("github_cache_write_skipped", file=path.name)

    # -- requests --------------------------------------------------------------

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one GraphQL query; return `data`. Partial errors (e.g. NOT_FOUND aliases) are logged."""
        variables = variables or {}
        path = self._cache_path(query, variables)
        cached = self._cache_read(path)
        if cached is not None:
            self.cache_hits += 1
            return cached
        if self._cache_mode == "replay":
            raise GitHubError("replay mode: query not in cache")
        data = self._post_with_retry(query, variables)
        self._cache_write(path, variables, data)
        return data

    def _post_with_retry(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        delay = 5.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = self._http.post(GRAPHQL_URL, json={"query": query, "variables": variables})
            except httpx.TransportError as exc:
                log.warning("github_transport_error", attempt=attempt, error=type(exc).__name__)
                self._sleep(delay)
                delay = min(delay * 2, MAX_SLEEP_SECONDS)
                continue
            self.requests_made += 1
            wait = self._retry_wait(resp, delay)
            if wait is not None:
                log.warning("github_backoff", attempt=attempt, status=resp.status_code, sleep_s=round(wait, 1))
                self._sleep(wait)
                delay = min(delay * 2, MAX_SLEEP_SECONDS)
                continue
            if resp.status_code != 200:
                raise GitHubError(f"GitHub GraphQL HTTP {resp.status_code}")
            body = resp.json()
            errors = body.get("errors") or []
            if any(e.get("type") == "RATE_LIMITED" for e in errors):
                wait = self._reset_wait(resp) or delay
                log.warning("github_rate_limited", attempt=attempt, sleep_s=round(wait, 1))
                self._sleep(wait)
                delay = min(delay * 2, MAX_SLEEP_SECONDS)
                continue
            data = body.get("data")
            if not isinstance(data, dict):
                kinds = sorted({str(e.get("type")) for e in errors})
                raise GitHubError(f"GitHub GraphQL returned no data (errors: {kinds})")
            if errors:
                log.info("github_partial_errors", count=len(errors), types=sorted({str(e.get("type")) for e in errors}))
            self._pace(resp)
            return data
        raise GitHubError(f"GitHub GraphQL failed after {MAX_ATTEMPTS} attempts")

    def _retry_wait(self, resp: httpx.Response, delay: float) -> float | None:
        status = resp.status_code
        if status in (502, 503, 504):
            return delay
        if status in (403, 429):
            retry_after = resp.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                return min(float(retry_after) + 1, MAX_SLEEP_SECONDS)
            if resp.headers.get("x-ratelimit-remaining") == "0":
                return self._reset_wait(resp) or delay
            if _is_secondary_limit(status, resp.text):
                return max(delay, 60.0)
        return None

    def _reset_wait(self, resp: httpx.Response) -> float | None:
        reset = resp.headers.get("x-ratelimit-reset")
        if reset and reset.isdigit():
            return min(max(float(reset) - time.time(), 0.0) + 2, MAX_SLEEP_SECONDS)
        return None

    def _pace(self, resp: httpx.Response) -> None:
        """Slow down when the primary budget runs low instead of hitting the wall."""
        remaining = resp.headers.get("x-ratelimit-remaining")
        if remaining and remaining.isdigit() and int(remaining) < 50:
            wait = self._reset_wait(resp)
            if wait:
                log.warning("github_budget_low", remaining=int(remaining), sleep_s=round(wait, 1))
                self._sleep(wait)
