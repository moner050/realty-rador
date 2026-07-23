import asyncio
import time


class RateLimiter:
    """Semaphore 기반 동시 요청 제어 + 최소 간격 보장 Rate Limiter.

    - max_concurrent: 동시에 허용할 최대 요청 수
    - interval_ms: 개별 요청 간 최소 간격 (밀리초)
    """

    def __init__(self, interval_ms: int = 30, max_concurrent: int = 30):
        self.interval_seconds = interval_ms / 1000.0
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_call_time: float = 0.0
        self._time_lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Semaphore 슬롯 획득 + 최소 간격 대기."""
        await self._semaphore.acquire()
        async with self._time_lock:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < self.interval_seconds:
                await asyncio.sleep(self.interval_seconds - elapsed)
            self._last_call_time = time.monotonic()

    def release(self) -> None:
        """Semaphore 슬롯 반환."""
        self._semaphore.release()
