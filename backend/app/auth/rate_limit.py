"""In-process sliding-window rate limiter.

Good enough for a single backend replica. Running several replicas would need
a shared store (e.g. Redis); callers only depend on ``hit()``, so swapping the
implementation does not touch the endpoints.
"""

import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    _SWEEP_THRESHOLD = 10_000

    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> bool:
        """Record an attempt; return False if ``key`` is over its limit."""
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > self._SWEEP_THRESHOLD:
            self._sweep(now)
        return True

    def retry_after(self, key: str) -> int:
        hits = self._hits.get(key)
        if not hits:
            return 0
        return max(1, int(hits[0] + self.window - self._clock()) + 1)

    def _sweep(self, now: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window]
        for key in stale:
            del self._hits[key]
