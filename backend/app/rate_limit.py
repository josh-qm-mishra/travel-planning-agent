import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class SlidingWindowLimiter:
    per_minute: int
    per_hour: int

    def __post_init__(self):
        self._data: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check_and_record(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds). retry_after=0 when allowed."""
        now = time.monotonic()
        async with self._lock:
            window = self._data[key]
            one_hour_ago = now - 3600
            while window and window[0] <= one_hour_ago:
                window.popleft()
            if len(window) >= self.per_hour:
                retry_after = max(1, int(window[0] + 3600 - now) + 1)
                return False, retry_after
            one_minute_ago = now - 60
            minute_count = sum(1 for t in window if t > one_minute_ago)
            if minute_count >= self.per_minute:
                oldest_in_minute = next(t for t in window if t > one_minute_ago)
                retry_after = max(1, int(oldest_in_minute + 60 - now) + 1)
                return False, retry_after
            window.append(now)
            return True, 0


_limiter: SlidingWindowLimiter | None = None


def init_limiter(per_minute: int, per_hour: int) -> SlidingWindowLimiter:
    global _limiter
    _limiter = SlidingWindowLimiter(per_minute=per_minute, per_hour=per_hour)
    return _limiter


def get_limiter() -> SlidingWindowLimiter:
    if _limiter is None:
        raise RuntimeError("Rate limiter not initialized")
    return _limiter
