"""Provider pacing, 429 handling and model fallback against a fake HTTP transport (no network)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.agent.provider import (
    WAIT_LISTENER,
    OpenAICompatibleProvider,
    RateLimiter,
    TokenLimiter,
    _duration_s,
    _empty,
    _tool_name,
    estimate_tokens,
    llm_configured,
    model_chain,
    pick_model,
    retry_after_s,
)
from app.errors import AppError
from app.settings import Settings
from app.worker.freshness import OpenAICompatibleLlm


def settings(**over: Any) -> Settings:
    base: dict[str, Any] = {
        "openai_api_key": SecretStr("test-key"),
        "openai_base_url": "https://llm.test/v1",
        "llm_model": "big",
        "llm_model_cheap": "small",
        "llm_fallback_models": "backup",
        "llm_max_retries": 2,
        "llm_requests_per_minute": 600,
    }
    return Settings(**(base | over))


def completion(model: str, text: str = "ok", tool: str | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": text}
    if tool:
        msg["tool_calls"] = [{"id": "c1", "type": "function", "function": {"name": tool, "arguments": "{}"}}]
    return {
        "id": "x", "object": "chat.completion", "created": 0, "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }  # fmt: skip


class Script:
    """Replies per model from a queue of (status, headers) or a success."""

    def __init__(self, plan: dict[str, list[tuple[int, dict[str, str]]]]) -> None:
        self.plan = {k: list(v) for k, v in plan.items()}
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        self.calls.append(model)
        queue = self.plan.get(model, [])
        status, headers = queue.pop(0) if queue else (200, {})
        if status == 200 and headers.get("empty"):
            return httpx.Response(200, json=completion(model, text=""))
        if status == 200:
            return httpx.Response(200, json=completion(model, tool="get_kep"))
        return httpx.Response(status, headers=headers, json={"error": {"message": "limited", "type": "x"}})


def provider(
    script: Script, sleeps: list[float], tokens: TokenLimiter | None = None, **over: Any
) -> OpenAICompatibleProvider:
    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    s = settings(**over)
    return OpenAICompatibleProvider(
        s,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(script)),
        limiter=RateLimiter(s.llm_requests_per_minute),
        tokens=tokens or TokenLimiter(),
        sleep=sleep,
    )


async def test_retry_after_is_honoured_then_succeeds() -> None:
    script = Script({"big": [(429, {"retry-after": "3"})]})
    sleeps: list[float] = []
    turn = await provider(script, sleeps).complete([{"role": "user", "content": "q"}], [])
    assert script.calls == ["big", "big"] and 3.0 in sleeps
    assert turn.tool_calls[0].name == "get_kep" and turn.input_tokens == 10


async def test_groq_reset_header_is_used() -> None:
    script = Script({"big": [(429, {"x-ratelimit-reset-tokens": "7.66s", "x-ratelimit-reset-requests": "2m0.5s"})]})
    sleeps: list[float] = []
    p = provider(script, sleeps, llm_max_retries=1)
    await p.complete([{"role": "user", "content": "q"}], [])
    # The 2-minute request window is ignored while requests remain; big is blocked for 7.66 s, so the cheap
    # model, free now, takes the request.
    assert script.calls == ["big", "small"] and p.last_model == "small" and not [s for s in sleeps if s > 30]


async def test_retries_are_bounded_then_fallback() -> None:
    script = Script({"big": [(429, {"retry-after": "1"})] * 5})
    sleeps: list[float] = []
    p = provider(script, sleeps)
    await p.complete([{"role": "user", "content": "q"}], [])
    assert script.calls == ["big", "big", "big", "small"] and p.last_model == "small"


async def test_all_models_limited_raises_rate_limited() -> None:
    script = Script({m: [(429, {"retry-after": "1"})] * 5 for m in ("big", "small", "backup")})
    with pytest.raises(AppError) as err:
        await provider(script, []).complete([{"role": "user", "content": "q"}], [])
    assert err.value.code == "provider_rate_limited"


async def test_missing_model_falls_back_and_bad_request_fails() -> None:
    script = Script({"big": [(404, {})]})
    p = provider(script, [])
    await p.complete([{"role": "user", "content": "q"}], [])
    assert p.last_model == "small"
    with pytest.raises(AppError) as err:
        await provider(Script({"big": [(401, {})]}), []).complete([{"role": "user", "content": "q"}], [])
    assert err.value.code == "provider_error"


async def test_server_error_backs_off() -> None:
    script = Script({"big": [(503, {})]})
    sleeps: list[float] = []
    await provider(script, sleeps).complete([{"role": "user", "content": "q"}], [])
    assert script.calls == ["big", "big"] and sleeps == [1.0]


async def test_spent_token_quota_switches_to_the_cheap_model_before_the_fallback() -> None:
    now = [0.0]
    tokens = TokenLimiter(clock=lambda: now[0])
    tokens.observe("big", httpx.Headers({"x-ratelimit-limit-tokens": "2000", "x-ratelimit-remaining-tokens": "0"}))
    script = Script({})
    sleeps: list[float] = []
    p = provider(script, sleeps, tokens)
    await p.complete([{"role": "user", "content": "q"}], [])
    assert script.calls == ["small"] and not sleeps


async def test_token_429_is_learned_and_waited_out_when_every_model_is_spent() -> None:
    now = [0.0]
    tokens = TokenLimiter(clock=lambda: now[0])
    for m in ("small", "backup"):
        tokens.observe(m, httpx.Headers({"x-ratelimit-remaining-tokens": "0"}))
    limited = {"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "20s", "retry-after": "20"}
    script = Script({"big": [(429, limited)]})
    sleeps: list[float] = []
    p = provider(script, sleeps, tokens)
    await p.complete([{"role": "user", "content": "q"}], [])
    # big needs 20 s; small and backup need the time to refill ~500 tokens (about 4 s), so small goes next.
    assert script.calls == ["big", "small"] and sleeps and 1 < sleeps[-1] < 20


async def test_long_waits_are_reported_to_the_listener() -> None:
    heard: list[float] = []

    async def listener(wait_s: float) -> None:
        heard.append(wait_s)

    token = WAIT_LISTENER.set(listener)
    try:
        await provider(Script({"big": [(429, {"retry-after": "3"})]}), []).complete(
            [{"role": "user", "content": "q"}], []
        )
    finally:
        WAIT_LISTENER.reset(token)
    assert heard == [pytest.approx(3.0)]


async def test_empty_turn_is_answered_by_another_model_family() -> None:
    script = Script({"openai/gpt-oss-120b": [(200, {"empty": "1"})]})
    over = {"llm_model": "openai/gpt-oss-120b", "llm_model_cheap": "openai/gpt-oss-20b"}
    p = provider(script, [], **over)
    tool = {"type": "function", "function": {"name": "get_kep", "parameters": {"type": "object"}}}
    turn = await p.complete([{"role": "user", "content": "q"}], [tool])
    assert script.calls == ["openai/gpt-oss-120b", "backup"] and turn.tool_calls[0].name == "get_kep"


def test_harmony_leaks_are_stripped_from_tool_names() -> None:
    assert _tool_name("functions.final_answer") == "final_answer"
    assert _tool_name("final_answer<|channel|>commentary") == "final_answer"


def test_token_limiter_refills_from_headers() -> None:
    now = [0.0]
    tokens = TokenLimiter(clock=lambda: now[0])
    tokens.observe("m", httpx.Headers({"x-ratelimit-limit-tokens": "6000", "x-ratelimit-remaining-tokens": "1000"}))
    assert tokens.wait_s("m", 1000) == 0.0
    assert tokens.wait_s("m", 2000) == pytest.approx(10.0)
    now[0] = 10.0
    assert tokens.wait_s("m", 2000) == 0.0
    tokens.reserve("m", 2000)
    assert tokens.wait_s("m", 100) == pytest.approx(1.0)
    tokens.block("m", 30.0)
    assert tokens.wait_s("m", 0) == pytest.approx(30.0)


def test_pick_model_prefers_a_short_wait_on_the_primary() -> None:
    now = [0.0]
    tokens = TokenLimiter(clock=lambda: now[0])
    tokens.observe("a", httpx.Headers({"x-ratelimit-remaining-tokens": "7700"}))
    assert pick_model(["a", "b"], 8000, tokens) == ("a", pytest.approx(2.25))
    tokens.observe("a", httpx.Headers({"x-ratelimit-remaining-tokens": "0"}))
    assert pick_model(["a", "b"], 8000, tokens) == ("b", 0.0)


def test_model_chain_and_estimate() -> None:
    s = settings()
    assert model_chain(s) == ["big", "small", "backup"] and model_chain(s, "small") == ["small", "backup"]
    assert estimate_tokens([{"role": "user", "content": "x" * 400}]) == pytest.approx(117, abs=3)


def test_token_bucket_paces_requests() -> None:
    now = [0.0]
    limiter = RateLimiter(2, clock=lambda: now[0])
    assert limiter.reserve() == 0.0 and limiter.reserve() == 0.0
    assert limiter.reserve() == pytest.approx(30.0)
    now[0] = 60.0
    assert limiter.reserve() == 0.0


async def test_every_model_far_away_fails_fast() -> None:
    day = {"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2h0m0s"}
    script = Script({m: [(429, day)] for m in ("big", "small", "backup")})
    sleeps: list[float] = []
    with pytest.raises(AppError) as err:
        await provider(script, sleeps).complete([{"role": "user", "content": "q"}], [])
    assert err.value.code == "provider_rate_limited" and script.calls == ["big", "small", "backup"] and not sleeps


def test_durations_and_headers() -> None:
    assert _duration_s("1m30s") == 90 and _duration_s("120ms") == pytest.approx(0.12) and _duration_s("2") == 2
    assert retry_after_s(httpx.Headers({"x-ratelimit-reset-requests": "4s", "x-ratelimit-reset-tokens": "9s"})) == 9
    assert retry_after_s(None) == 2.0


def test_not_configured_without_key() -> None:
    s = settings(openai_api_key=None)
    assert not llm_configured(s)
    with pytest.raises(AppError) as err:
        OpenAICompatibleProvider(s)
    assert err.value.code == "llm_not_configured"


def test_freshness_llm_uses_the_shared_policy() -> None:
    script = Script({"small": [(429, {"retry-after": "0"})]})
    llm = OpenAICompatibleLlm(settings(), http_client=httpx.Client(transport=httpx.MockTransport(script)))
    out = llm.complete([{"role": "user", "content": "q"}])
    assert script.calls == ["small", "small"] and out.text == "ok" and out.input_tokens == 10


def test_whitespace_only_reply_counts_as_empty() -> None:
    from types import SimpleNamespace

    def resp(content: str | None, tool_calls: list[object] | None = None) -> object:
        message = SimpleNamespace(content=content, tool_calls=tool_calls)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    assert _empty(resp("\n\n")) and _empty(resp(None))
    assert not _empty(resp("It is provisional.")) and not _empty(resp("", [object()]))
