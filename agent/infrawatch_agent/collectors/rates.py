"""Turn monotonically increasing kernel counters into per-second rates."""

import time
from collections.abc import Callable, Iterable


class CounterRates:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._previous: dict[str, tuple[float, float]] = {}

    def rate(self, key: str, value: float, now: float | None = None) -> float:
        now = self._clock() if now is None else now
        previous = self._previous.get(key)
        self._previous[key] = (value, now)
        if previous is None:
            return 0.0
        delta, elapsed = value - previous[0], now - previous[1]
        # A decreasing counter means it was reset (interface re-created, driver
        # reload, 32-bit wrap). Report 0 for this interval rather than a huge
        # negative or bogus rate.
        if elapsed <= 0 or delta < 0:
            return 0.0
        return delta / elapsed

    def forget_except(self, live_prefixes: Iterable[str]) -> None:
        """Drop state for devices that disappeared (e.g. unplugged USB NIC)."""
        live = tuple(live_prefixes)
        for key in [k for k in self._previous if not k.startswith(live)]:
            del self._previous[key]
