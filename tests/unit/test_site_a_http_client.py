import asyncio

import httpx
import pytest

from realty_radar.crawler.adapters.site_a.http_client import (
    NaverCredentials,
    NaverHttpClient,
    RetryWaitError,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Bootstrap:
    def __init__(self):
        self.calls = 0

    async def __call__(self) -> NaverCredentials:
        self.calls += 1
        return NaverCredentials(authorization=f"Bearer token-{self.calls}", cookies=())


@pytest.mark.anyio
async def test_refresh_applies_non_sensitive_browser_headers_to_httpx_requests():
    class BrowserHeaderBootstrap:
        async def __call__(self) -> NaverCredentials:
            return NaverCredentials(
                authorization="Bearer token",
                cookies=(),
                request_headers={
                    "Accept-Language": "ko-KR",
                    "Referer": "https://new.land.naver.com/complexes/1001",
                    "Sec-CH-UA": '"Chromium";v="124"',
                },
            )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-language"] == "ko-KR"
        assert request.headers["referer"] == "https://new.land.naver.com/complexes/1001"
        assert request.headers["sec-ch-ua"] == '"Chromium";v="124"'
        return httpx.Response(200, json={"ok": True})

    client = NaverHttpClient(BrowserHeaderBootstrap(), transport=httpx.MockTransport(handler), retry_backoff_seconds=0)
    try:
        assert await client.get_json("https://new.land.naver.com/api/test") == {"ok": True}
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_401_refreshes_once_then_reuses_the_refreshed_session():
    bootstrap = Bootstrap()
    seen_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("authorization")
        seen_tokens.append(token)
        if token == "Bearer token-1":
            return httpx.Response(401, json={"error": "expired"})
        return httpx.Response(200, json={"ok": True})

    client = NaverHttpClient(bootstrap, transport=httpx.MockTransport(handler), retry_backoff_seconds=0)
    try:
        assert await client.get_json("https://new.land.naver.com/api/test") == {"ok": True}
        assert bootstrap.calls == 2
        assert seen_tokens == ["Bearer token-1", "Bearer token-2"]
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_429_halves_concurrency_and_retries_with_retry_after():
    bootstrap = Bootstrap()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow down"})
        return httpx.Response(200, json={"ok": True})

    client = NaverHttpClient(bootstrap, transport=httpx.MockTransport(handler), retry_backoff_seconds=0)
    try:
        assert await client.get_json("https://new.land.naver.com/api/test") == {"ok": True}
        assert client.concurrency_limit == 4
        assert attempts == 2
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_repeated_403_opens_retry_wait_circuit_after_one_refresh():
    bootstrap = Bootstrap()

    client = NaverHttpClient(
        bootstrap,
        transport=httpx.MockTransport(lambda request: httpx.Response(403, json={"error": "forbidden"})),
        retry_backoff_seconds=0,
    )
    try:
        with pytest.raises(RetryWaitError):
            await client.get_json("https://new.land.naver.com/api/test")
        assert bootstrap.calls == 2
        with pytest.raises(RetryWaitError):
            await client.get_json("https://new.land.naver.com/api/test")
        assert bootstrap.calls == 2
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_5xx_retries_but_cancellation_is_not_retried():
    bootstrap = Bootstrap()
    attempts = 0

    def retry_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500 if attempts < 3 else 200, json={"ok": attempts == 3})

    client = NaverHttpClient(bootstrap, transport=httpx.MockTransport(retry_handler), retry_backoff_seconds=0)
    try:
        assert await client.get_json("https://new.land.naver.com/api/test") == {"ok": True}
        assert attempts == 3
    finally:
        await client.aclose()

    cancel_attempts = 0

    async def cancelled_handler(request: httpx.Request) -> httpx.Response:
        nonlocal cancel_attempts
        cancel_attempts += 1
        raise asyncio.CancelledError

    cancelled = NaverHttpClient(
        bootstrap,
        transport=httpx.MockTransport(cancelled_handler),
        retry_backoff_seconds=0,
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await cancelled.get_json("https://new.land.naver.com/api/test")
        assert cancel_attempts == 1
    finally:
        await cancelled.aclose()
