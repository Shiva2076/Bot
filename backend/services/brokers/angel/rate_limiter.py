import asyncio
import time
from collections import deque
from typing import Deque, Optional


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: Deque[float] = deque()
        self._lock: Optional[asyncio.Lock] = None

    async def acquire(self) -> None:
        self._lock = self._lock or asyncio.Lock()
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self._window_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._max_requests:
                    self._timestamps.append(now)
                    return
                await asyncio.sleep(self._window_seconds - (now - self._timestamps[0]))
