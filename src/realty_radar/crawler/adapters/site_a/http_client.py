"""Playwright bootstrap 자격 증명을 사용하는 SITE_A httpx transport."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from time import monotonic
from typing import Any, AsyncIterator, Awaitable, Callable, Mapping

import httpx


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class NaverHttpError(RuntimeError):
    """SITE_A API가 정상 JSON 응답을 반환하지 않았을 때의 기본 오류."""


class AuthenticationError(NaverHttpError):
    """한 번의 session refresh 후에도 인증이 복구되지 않았다."""


class RetryWaitError(NaverHttpError):
    """403 반복 등으로 circuit breaker가 열린 상태다."""


@dataclass(frozen=True, slots=True)
class NaverCookie:
    name: str
    value: str
    domain: str
    path: str = "/"


@dataclass(frozen=True, slots=True)
class NaverCredentials:
    """로그·파일·DB로 직렬화하지 않는 메모리 전용 bootstrap 결과."""

    authorization: str
    cookies: tuple[NaverCookie, ...]


class AdaptiveConcurrency:
    """50회 연속 성공 시 +1, 429 시 절반으로 줄이는 async permit."""

    def __init__(self, initial: int = 8, minimum: int = 4, maximum: int = 32):
        self.minimum = minimum
        self.maximum = maximum
        self.limit = max(minimum, min(maximum, initial))
        self._active = 0
        self._successes = 0
        self._condition = asyncio.Condition()

    @asynccontextmanager
    async def permit(self) -> AsyncIterator[None]:
        async with self._condition:
            await self._condition.wait_for(lambda: self._active < self.limit)
            self._active += 1
        try:
            yield
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify_all()

    async def record_success(self) -> None:
        async with self._condition:
            self._successes += 1
            if self._successes >= 50 and self.limit < self.maximum:
                self.limit += 1
                self._successes = 0
                self._condition.notify_all()

    async def record_throttle(self) -> None:
        async with self._condition:
            self.limit = max(self.minimum, self.limit // 2)
            self._successes = 0
            self._condition.notify_all()


Bootstrap = Callable[[], Awaitable[NaverCredentials]]


class NaverHttpClient:
    """재사용 connection pool과 인증 refresh lock을 가진 SITE_A JSON client."""

    def __init__(
        self,
        bootstrap: Bootstrap,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
        retry_backoff_seconds: float = 0.25,
        circuit_open_seconds: float = 300,
    ):
        self._bootstrap = bootstrap
        self._refresh_lock = asyncio.Lock()
        self._generation = 0
        self._started = False
        self._circuit_open_until = 0.0
        self._retry_backoff_seconds = retry_backoff_seconds
        self._circuit_open_seconds = circuit_open_seconds
        self._limiter = AdaptiveConcurrency(initial=8, minimum=4, maximum=32)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=15.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=32),
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json, text/plain, */*"},
            follow_redirects=True,
            transport=transport,
        )

    @property
    def concurrency_limit(self) -> int:
        return self._limiter.limit

    async def aclose(self) -> None:
        await self._client.aclose()

    async def refresh_session(self) -> None:
        """새 job 시작 시 새 browser context에서 얻은 자격 증명으로만 갱신한다."""
        await self._refresh(expected_generation=None)

    async def get_json(self, url: str, *, params: Mapping[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        if monotonic() < self._circuit_open_until:
            raise RetryWaitError("SITE_A HTTP circuit is open; retry the job later")
        if not self._started:
            await self._refresh(expected_generation=None)

        generation = self._generation
        did_refresh_401 = False
        did_refresh_403 = False
        retry_attempt = 0

        while True:
            try:
                async with self._limiter.permit():
                    response = await self._client.get(url, params=params)
            except asyncio.CancelledError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if retry_attempt >= 2:
                    raise NaverHttpError(f"SITE_A request failed after retries: {type(error).__name__}") from error
                await self._backoff(retry_attempt)
                retry_attempt += 1
                continue

            if 200 <= response.status_code < 300:
                return await self._decode_json(response)

            if response.status_code == 401:
                if did_refresh_401:
                    raise AuthenticationError("SITE_A stayed unauthorized after one session refresh")
                await self._refresh(expected_generation=generation)
                generation = self._generation
                did_refresh_401 = True
                continue

            if response.status_code == 403:
                if did_refresh_403:
                    self._circuit_open_until = monotonic() + self._circuit_open_seconds
                    raise RetryWaitError("SITE_A denied the refreshed session; retry the job later")
                await self._refresh(expected_generation=generation)
                generation = self._generation
                did_refresh_403 = True
                continue

            if response.status_code == 429:
                await self._limiter.record_throttle()
                if retry_attempt >= 2:
                    raise NaverHttpError("SITE_A kept returning HTTP 429")
                await self._retry_after(response, retry_attempt)
                retry_attempt += 1
                continue

            if 500 <= response.status_code < 600:
                if retry_attempt >= 2:
                    raise NaverHttpError(f"SITE_A returned HTTP {response.status_code} after retries")
                await self._backoff(retry_attempt)
                retry_attempt += 1
                continue

            raise NaverHttpError(f"SITE_A returned HTTP {response.status_code}")

    async def _decode_json(self, response: httpx.Response) -> dict[str, Any] | list[Any]:
        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            raise NaverHttpError("SITE_A returned a non-JSON success response")
        try:
            payload = response.json()
        except ValueError as error:
            raise NaverHttpError("SITE_A returned invalid JSON") from error
        if not isinstance(payload, (dict, list)):
            raise NaverHttpError("SITE_A JSON payload must be an object or array")
        await self._limiter.record_success()
        return payload

    async def _refresh(self, expected_generation: int | None) -> None:
        async with self._refresh_lock:
            if expected_generation is not None and self._generation != expected_generation:
                return
            credentials = await self._bootstrap()
            if not credentials.authorization:
                raise AuthenticationError("SITE_A bootstrap did not capture Authorization")
            self._client.headers["Authorization"] = credentials.authorization
            self._client.cookies.clear()
            for cookie in credentials.cookies:
                self._client.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
            self._generation += 1
            self._started = True
            self._circuit_open_until = 0.0

    async def _retry_after(self, response: httpx.Response, retry_attempt: int) -> None:
        raw = response.headers.get("retry-after")
        delay = self._retry_backoff_seconds * (2**retry_attempt)
        if raw:
            try:
                delay = max(delay, float(raw))
            except ValueError:
                try:
                    delay = max(delay, (parsedate_to_datetime(raw) - datetime.now(parsedate_to_datetime(raw).tzinfo)).total_seconds())
                except (TypeError, ValueError):
                    pass
        if delay > 0:
            await asyncio.sleep(delay)

    async def _backoff(self, retry_attempt: int) -> None:
        delay = self._retry_backoff_seconds * (2**retry_attempt)
        if delay > 0:
            await asyncio.sleep(delay)
