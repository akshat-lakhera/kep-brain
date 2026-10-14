"""LLM provider adapters (02 §6.1).

The agent loop speaks one internal format (OpenAI chat messages with tool
calls). `openai_compatible` sends it to an OpenAI-compatible endpoint (Groq by
default, key `OPENAI_API_KEY`); `anthropic` translates it to the Messages API
and is available only when `ANTHROPIC_API_KEY` is set and the SDK is installed.

Rate limits: one process-wide bucket paces requests (`LLM_REQUESTS_PER_MINUTE`)
and a per-model tokens-per-minute ledger (`TokenLimiter`) learns each model's
quota from the `x-ratelimit-*-tokens` headers. Before a call the policy picks
the first model in the chain (primary, cheap, `LLM_FALLBACK_MODELS`; each has
its own quota on Groq) whose quota fits the request now, or waits for the one
that frees up first. A 429 updates the ledger and blocks that model for the
wait the provider asks for (at most `LLM_MAX_RETRIES` times per model); the
request fails only when every remaining model is further than `MAX_WAIT_S`
away. The api (async) and the freshness worker (sync) share the limiters, the
retry policy and one client per mode.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import re
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
import openai
import structlog

from app.errors import AppError
from app.settings import Settings

log = structlog.get_logger(__name__)

# USD per million tokens (input, output), Groq list prices; used only for the daily spend counter.
PRICES: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b": (0.10, 0.50),
    "llama-3.1-8b-instant": (0.05, 0.08),
}
DEFAULT_PRICE = (0.59, 0.79)
# The longest the policy sleeps for a quota before giving up (a full tokens-per-minute refill takes 60 s).
MAX_WAIT_S = 60.0
# A wait on the preferred model this short beats switching to a weaker one.
PREFER_WAIT_S = 4.0
# Groq free tier, measured 2026-10-15 for all three models; replaced by the headers after the first call.
DEFAULT_TOKENS_PER_MINUTE = 8000
MAX_OUTPUT_TOKENS = 1500
# Groq does not reserve max_tokens against the quota (measured); budget for a typical turn's output instead.
EXPECTED_OUTPUT_TOKENS = 500
SERVER_ERROR_BACKOFF_S = (1.0, 2.0, 4.0)
# Groq 400 codes for a malformed generation (not a malformed request).
REGENERATE_CODES = ("tool_use_failed", "output_parse_failed")


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    raw_message: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str
    model: str

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn: ...


# Measured on this agent's JSON-heavy prompts: Groq bills about one token per 3.5 characters.
CHARS_PER_TOKEN = 3.5


def estimate_tokens(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> int:
    """Rough prompt size used for budgeting; tool specs count too."""
    chars = sum(len(str(m.get("content") or "")) + len(json.dumps(m.get("tool_calls", ""))) + 8 for m in messages)
    if tools:
        chars += len(json.dumps(tools, separators=(",", ":")))
    return int(chars / CHARS_PER_TOKEN) + 1


def resolve_openai_key(settings: Settings) -> str | None:
    return settings.openai_api_key.get_secret_value() if settings.openai_api_key is not None else None


def llm_configured(settings: Settings) -> bool:
    if settings.llm_provider == "anthropic":
        return settings.anthropic_api_key is not None
    return resolve_openai_key(settings) is not None


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES.get(model, DEFAULT_PRICE)
    return (input_tokens * pin + output_tokens * pout) / 1_000_000


def _parse_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"__invalid_json__": raw[:500]}
    return value if isinstance(value, dict) else {"__invalid_json__": raw[:500]}


# -- pacing ------------------------------------------------------------------------------------------


class RateLimiter:
    """Token bucket: `per_minute` requests, refilled continuously, shared by threads and event loops."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._tokens = self.capacity
        self._clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def reserve(self) -> float:
        """Take one token now (possibly going negative) and return how long the caller must wait."""
        with self._lock:
            now = self._clock()
            self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
            self._last = now
            self._tokens -= 1.0
            return 0.0 if self._tokens >= 0 else -self._tokens / self.rate


_LIMITER: RateLimiter | None = None
_LIMITER_LOCK = threading.Lock()


def shared_limiter(settings: Settings) -> RateLimiter:
    global _LIMITER
    with _LIMITER_LOCK:
        if _LIMITER is None or _LIMITER.capacity != settings.llm_requests_per_minute:
            _LIMITER = RateLimiter(settings.llm_requests_per_minute)
        return _LIMITER


class TokenLimiter:
    """Per-model tokens-per-minute ledger fed by `x-ratelimit-{limit,remaining}-tokens`.

    Groq refills the token quota continuously, so the tokens available at time t are
    `remaining + elapsed * limit / 60`, capped at `limit`.
    """

    def __init__(self, default_limit: int = DEFAULT_TOKENS_PER_MINUTE, clock: Callable[[], float] = time.monotonic):
        self.default_limit = default_limit
        self._clock = clock
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float, float]] = {}  # model -> (limit, remaining, at)
        self._blocked_until: dict[str, float] = {}

    def _available(self, model: str, now: float) -> tuple[int, float]:
        limit, remaining, at = self._state.get(model, (self.default_limit, float(self.default_limit), now))
        return limit, min(float(limit), remaining + (now - at) * limit / 60.0)

    def wait_s(self, model: str, need: int) -> float:
        with self._lock:
            now = self._clock()
            limit, available = self._available(model, now)
            need = min(need, limit)
            tokens_wait = 0.0 if available >= need else (need - available) * 60.0 / limit
            return max(tokens_wait, self._blocked_until.get(model, now) - now)

    def block(self, model: str, seconds: float) -> None:
        with self._lock:
            self._blocked_until[model] = self._clock() + seconds

    def reserve(self, model: str, need: int) -> None:
        with self._lock:
            now = self._clock()
            limit, available = self._available(model, now)
            self._state[model] = (limit, available - min(need, limit), now)

    def observe(self, model: str, headers: Mapping[str, str] | None, *, limited: bool = False) -> None:
        """Take the provider's numbers; after a 429 the quota counts as refilling until `reset-tokens`."""
        h: Mapping[str, str] = headers if headers is not None else {}
        with self._lock:
            now = self._clock()
            limit, remaining = self._available(model, now)
            limit = int(_header_number(h, "x-ratelimit-limit-tokens") or limit)
            reported = _header_number(h, "x-ratelimit-remaining-tokens")
            remaining = reported if reported is not None else remaining
            reset = _duration_s(h.get("x-ratelimit-reset-tokens", ""))
            if limited and reset is not None:
                remaining = min(remaining, limit - reset * limit / 60.0)
            self._state[model] = (limit, remaining, now)


def _header_number(headers: Mapping[str, str], name: str) -> float | None:
    try:
        return float(headers[name])
    except (KeyError, ValueError):
        return None


_TOKENS: TokenLimiter | None = None


def shared_token_limiter() -> TokenLimiter:
    global _TOKENS
    with _LIMITER_LOCK:
        if _TOKENS is None:
            _TOKENS = TokenLimiter()
        return _TOKENS


_DURATION = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$")


def _duration_s(value: str) -> float | None:
    """`2.5s`, `1m30s`, `120ms`, `7.66s` (Groq `x-ratelimit-reset-*`) or plain seconds (`Retry-After`)."""
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    m = _DURATION.match(value)
    if not m or not any(m.groups()):
        return None
    h, mi, s, ms = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000


def retry_after_s(headers: Mapping[str, str] | None) -> float:
    """The wait a 429 asks for: `Retry-After`, else `x-ratelimit-reset-tokens`, else 2 s. The request window
    (`x-ratelimit-reset-requests`, up to a day on Groq) counts only when no requests remain."""
    if headers is None:
        return 2.0
    ra = headers.get("retry-after")
    if ra is not None and (v := _duration_s(ra)) is not None:
        return v
    names = ["x-ratelimit-reset-tokens"]
    if headers.get("x-ratelimit-remaining-requests") == "0":
        names.append("x-ratelimit-reset-requests")
    known = [d for h in names if h in headers and (d := _duration_s(headers[h])) is not None]
    return max(known) if known else 2.0


# -- retry and fallback policy (shared by the async and sync clients) --------------------------------


@dataclass
class Attempt:
    """What to do after a failed call: wait and retry the same model, move on, or give up."""

    action: str  # "retry" | "next_model" | "fail"
    wait_s: float = 0.0
    code: str = "provider_error"


def classify(exc: Exception, retries_done: int, max_retries: int) -> Attempt:
    if isinstance(exc, openai.RateLimitError):
        wait = retry_after_s(exc.response.headers if exc.response is not None else None)
        if retries_done < max_retries:
            return Attempt("retry", wait, "provider_rate_limited")
        return Attempt("next_model", 0.0, "provider_rate_limited")
    if isinstance(exc, openai.InternalServerError | openai.APIConnectionError):
        if retries_done < min(max_retries, len(SERVER_ERROR_BACKOFF_S)):
            return Attempt("retry", SERVER_ERROR_BACKOFF_S[retries_done], "provider_error")
        return Attempt("next_model", 0.0, "provider_error")
    if isinstance(exc, openai.NotFoundError):
        return Attempt("next_model", 0.0, "provider_error")
    if isinstance(exc, openai.BadRequestError) and "decommission" in str(exc).lower():
        return Attempt("next_model", 0.0, "provider_error")
    if isinstance(exc, openai.BadRequestError) and any(
        c in str(exc) for c in ("tool_use_failed", "output_parse_failed")
    ):
        # The model emitted malformed output or tool call; sampling again usually fixes it.
        return Attempt("retry" if retries_done < 1 else "next_model", 0.0, "provider_error")
    return Attempt("fail", 0.0, "provider_error")


def model_chain(settings: Settings, primary: str | None = None) -> list[str]:
    """Primary, then the cheap model (a separate quota on Groq), then the configured fallbacks."""
    head = [primary] if primary else [settings.llm_model, settings.llm_model_cheap]
    return list(dict.fromkeys([*head, *settings.llm_fallback_list]))


Sleep = Callable[[float], Awaitable[None]]

# Set by the agent loop for one ask: told how long the policy is about to wait for a model's quota.
WAIT_LISTENER: contextvars.ContextVar[Callable[[float], Awaitable[None]] | None] = contextvars.ContextVar(
    "llm_wait_listener", default=None
)
# Waits shorter than this are not worth telling the user about.
NOTIFY_WAIT_S = 1.0


def pick_model(models: list[str], need: int, tokens: TokenLimiter) -> tuple[str, float]:
    """The preferred model if its quota frees up within PREFER_WAIT_S, else the first one free now,
    else whichever frees up first."""
    waits = [(m, tokens.wait_s(m, need)) for m in models]
    if waits[0][1] <= PREFER_WAIT_S:
        return waits[0]
    free = [w for w in waits if w[1] == 0.0]
    return free[0] if free else min(waits, key=lambda w: w[1])


async def call_with_policy(
    settings: Settings,
    models: list[str],
    send: Callable[[str], Awaitable[Any]],
    *,
    need_tokens: int = 0,
    limiter: RateLimiter | None = None,
    tokens: TokenLimiter | None = None,
    sleep: Sleep = asyncio.sleep,
) -> tuple[str, Any]:
    limiter = limiter or shared_limiter(settings)
    tokens = tokens or shared_token_limiter()
    alive = list(models)
    retries = dict.fromkeys(models, 0)
    last = Attempt("fail")
    while alive:
        model, wait = pick_model(alive, need_tokens, tokens)
        if wait > MAX_WAIT_S:
            log.warning("provider_quota_wait_too_long", model=model, wait_s=round(wait, 1))
            raise AppError("provider_rate_limited")
        if wait > 0:
            log.info("provider_wait", model=model, wait_s=round(wait, 2), need_tokens=need_tokens)
            if wait >= NOTIFY_WAIT_S and (listener := WAIT_LISTENER.get()) is not None:
                await listener(wait)
            await sleep(wait)
        if (pace := limiter.reserve()) > 0:
            await sleep(pace)
        tokens.reserve(model, need_tokens)
        try:
            return model, await send(model)
        except openai.APIError as exc:
            last = classify(exc, retries[model], settings.llm_max_retries)
            status = exc.status_code if isinstance(exc, openai.APIStatusError) else None
            log.warning("provider_call_failed", model=model, action=last.action, wait_s=round(last.wait_s, 2),
                        error=type(exc).__name__, status=status, need_tokens=need_tokens,
                        detail=_limit_kind(exc) if status == 429 else ascii(str(exc)[:300]))  # fmt: skip
            if isinstance(exc, openai.RateLimitError):
                tokens.observe(model, exc.response.headers if exc.response is not None else None, limited=True)
            if last.action == "fail":
                raise AppError(last.code) from exc
            if last.action == "retry":
                retries[model] += 1
                tokens.block(model, last.wait_s)
            else:
                alive.remove(model)
    raise AppError(last.code)


def call_with_policy_sync(
    settings: Settings,
    models: list[str],
    send: Callable[[str], Any],
    *,
    limiter: RateLimiter | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str, Any]:
    async def asend(model: str) -> Any:
        return send(model)

    async def asleep(seconds: float) -> None:
        sleep(seconds)

    return asyncio.run(call_with_policy(settings, models, asend, limiter=limiter, sleep=asleep))


# -- clients -----------------------------------------------------------------------------------------

_CLIENTS: dict[tuple[str, str], Any] = {}
_CLIENTS_LOCK = threading.Lock()


def _client(settings: Settings, mode: str, http_client: Any = None) -> Any:
    key = resolve_openai_key(settings)
    if key is None:
        raise AppError("llm_not_configured")
    kwargs: dict[str, Any] = {"api_key": key, "base_url": settings.openai_base_url,
                              "timeout": settings.llm_timeout_seconds, "max_retries": 0}  # fmt: skip
    if http_client is not None:
        kwargs["http_client"] = http_client
        return openai.AsyncOpenAI(**kwargs) if mode == "async" else openai.OpenAI(**kwargs)
    cache_key = (mode, settings.openai_base_url or "")
    with _CLIENTS_LOCK:
        if cache_key not in _CLIENTS:
            _CLIENTS[cache_key] = openai.AsyncOpenAI(**kwargs) if mode == "async" else openai.OpenAI(**kwargs)
        return _CLIENTS[cache_key]


def sync_client(settings: Settings, http_client: httpx.Client | None = None) -> openai.OpenAI:
    client: openai.OpenAI = _client(settings, "sync", http_client)
    return client


def reasoning_params(model: str) -> dict[str, Any]:
    """Keep hidden reasoning short: it is billed against the same tokens-per-minute quota."""
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    if model.startswith("qwen/"):
        return {"reasoning_format": "hidden"}
    return {}


def _limit_kind(exc: Exception) -> str:
    """Which Groq quota a 429 hit; the daily ones (TPD, RPD) are not in the x-ratelimit headers."""
    text = str(exc)
    for code, kind in (("(TPD)", "tokens_per_day"), ("(RPD)", "requests_per_day"), ("(TPM)", "tokens_per_minute"),
                       ("(RPM)", "requests_per_minute")):  # fmt: skip
        if code in text:
            return kind
    return "unknown"


def _empty(resp: Any) -> bool:
    return bool(resp.choices) and not resp.choices[0].message.content and not resp.choices[0].message.tool_calls


def _family(model: str) -> str:
    return model.rsplit("-", 1)[0]


def _tool_name(name: str) -> str:
    """gpt-oss sometimes leaks its harmony syntax into the name: `functions.final_answer`, `x<|channel|>...`."""
    return name.split("<|", 1)[0].removeprefix("functions.")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        model: str | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
        tokens: TokenLimiter | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self.model = model or settings.llm_model
        self.last_model = self.model
        self._primary = model
        self._client = _client(settings, "async", http_client)
        self._limiter = limiter
        self._tokens = tokens or shared_token_limiter()
        self._sleep = sleep

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
        async def send(model: str) -> Any:
            raw = await self._client.chat.completions.with_raw_response.create(
                model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0.1,
                max_tokens=MAX_OUTPUT_TOKENS, extra_body=reasoning_params(model),
            )  # fmt: skip
            self._tokens.observe(model, raw.headers)
            return raw.parse()

        need = estimate_tokens(messages, tools) + EXPECTED_OUTPUT_TOKENS
        chain = model_chain(self.settings, self._primary)

        async def run(models: list[str]) -> tuple[str, Any]:
            return await call_with_policy(self.settings, models, send, need_tokens=need, limiter=self._limiter,
                                          tokens=self._tokens, sleep=self._sleep)  # fmt: skip

        model, resp = await run(chain)
        if tools and _empty(resp):
            # gpt-oss on Groq sometimes reasons to an answer and then emits nothing, deterministically for the
            # same prompt; another model family answers it.
            msg = resp.choices[0].message
            log.warning("provider_empty_turn", model=model, finish_reason=resp.choices[0].finish_reason,
                        reasoning=ascii(str(getattr(msg, "reasoning", ""))[-300:]))  # fmt: skip
            others = [m for m in chain if _family(m) != _family(model)]
            if others:
                model, resp = await run(others)
        self.last_model = model
        if not resp.choices:
            raise AppError("provider_error", {"reason": "empty response"})
        msg = resp.choices[0].message
        calls = [
            ToolCall(id=c.id or f"call_{i}", name=_tool_name(c.function.name),
                     arguments=_parse_args(c.function.arguments), raw_arguments=c.function.arguments or "")
            for i, c in enumerate(msg.tool_calls or [])
            if getattr(c, "function", None) is not None
        ]  # fmt: skip
        raw: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if calls:
            raw["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw_arguments or "{}"}}
                for c in calls
            ]
        usage = resp.usage
        return Turn(
            text=msg.content or "",
            tool_calls=calls,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            raw_message=raw,
        )


class AnthropicProvider:
    """Messages API adapter; the internal OpenAI-shaped history is translated per call."""

    name = "anthropic"

    def __init__(self, settings: Settings, model: str | None = None) -> None:
        if settings.anthropic_api_key is None:
            raise AppError("llm_not_configured")
        try:
            import anthropic
        except ImportError as exc:
            raise AppError("llm_not_configured", {"reason": "anthropic SDK not installed"}) from exc
        self.model = model or settings.llm_model
        self._anthropic = anthropic
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(), timeout=settings.llm_timeout_seconds
        )

    @staticmethod
    def _translate(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            if role == "system":
                system_parts.append(m["content"])
            elif role == "user":
                out.append({"role": "user", "content": m["content"]})
            elif role == "assistant":
                blocks: list[dict[str, Any]] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for c in m.get("tool_calls", []):
                    blocks.append({"type": "tool_use", "id": c["id"], "name": c["function"]["name"],
                                   "input": _parse_args(c["function"]["arguments"])})  # fmt: skip
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            elif role == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return "\n\n".join(system_parts), out

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Turn:
        anthropic = self._anthropic
        system, msgs = self._translate(messages)
        atools = [
            {"name": t["function"]["name"], "description": t["function"]["description"],
             "input_schema": t["function"]["parameters"]}
            for t in tools
        ]  # fmt: skip
        try:
            resp = await self._client.messages.create(
                model=self.model, max_tokens=4096, system=system, messages=msgs, tools=atools
            )
        except anthropic.RateLimitError as exc:
            raise AppError("provider_rate_limited") from exc
        except anthropic.APIError as exc:
            log.warning("provider_error", error=str(exc)[:300])
            raise AppError("provider_error") from exc
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=dict(b.input), raw_arguments=json.dumps(b.input))
            for b in resp.content
            if b.type == "tool_use"
        ]
        raw: dict[str, Any] = {"role": "assistant", "content": text}
        if calls:
            raw["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.raw_arguments}}
                for c in calls
            ]
        return Turn(
            text=text,
            tool_calls=calls,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            raw_message=raw,
        )


def make_provider(settings: Settings) -> Provider:
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings)
    return OpenAICompatibleProvider(settings)
