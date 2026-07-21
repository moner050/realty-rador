import asyncio
import time


class RateLimiter:
    """사이트별 최소 요청 간격 준수를 위한 비동기 락/딜레이 관리자."""

    def __init__(self, interval_ms: int = 3000):
        self.interval_seconds = interval_ms / 1000.0
        self._last_call_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """요청 실행 전 필요한 간격만큼 대기."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_time
            if elapsed < self.interval_seconds:
                await asyncio.sleep(self.interval_seconds - elapsed)
            self._last_call_time = time.monotonic()
