"""Exponential backoff with "equal jitter".

ceiling = min(cap, base * 2^failures);  delay = random(ceiling / 2, ceiling)

Jitter spreads reconnect attempts so a fleet of agents does not stampede a
server that just came back up. The cap keeps an agent from waiting longer than
``cap`` seconds to notice that the server has recovered.
"""

import random
import time
from collections.abc import Callable


class Backoff:
    def __init__(
        self,
        base: float = 2.0,
        cap: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
        rng: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.base = base
        self.cap = cap
        self.failures = 0
        self._clock = clock
        self._rng = rng
        self._next_attempt = 0.0

    def ready(self) -> bool:
        return self._clock() >= self._next_attempt

    def failure(self, minimum: float = 0.0) -> float:
        """Record a failure; return the delay until the next attempt."""
        self.failures += 1
        ceiling = min(self.cap, self.base * 2 ** min(self.failures, 20))
        delay = max(minimum, self._rng(ceiling / 2, ceiling))
        self._next_attempt = self._clock() + delay
        return delay

    def success(self) -> None:
        self.failures = 0
        self._next_attempt = 0.0

    @property
    def seconds_until_retry(self) -> float:
        return max(0.0, self._next_attempt - self._clock())
