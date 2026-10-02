"""Memory from /proc/meminfo.

"Used" is defined as ``MemTotal - MemAvailable``: memory that could not be
handed to a new workload without swapping. Page cache is reclaimable and is
deliberately *not* counted as used, which is what ``free``'s "available"
column and modern monitoring tools agree on.
"""

from typing import Any

from infrawatch_agent.collectors.base import HostPaths, read_text


def parse_meminfo(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            multiplier = 1024 if len(parts) > 1 and parts[1] == "kB" else 1
            values[key.strip()] = int(parts[0]) * multiplier
    return values


class MemoryCollector:
    name = "memory"

    def __init__(self, paths: HostPaths) -> None:
        self._paths = paths

    def prime(self) -> None:
        pass

    def collect(self) -> dict[str, Any]:
        info = parse_meminfo(read_text(self._paths.proc / "meminfo") or "")
        total = info["MemTotal"]
        # MemAvailable exists since Linux 3.14; estimate it on older kernels.
        available = info.get(
            "MemAvailable", info.get("MemFree", 0) + info.get("Cached", 0) + info.get("Buffers", 0)
        )
        swap_total = info.get("SwapTotal", 0)
        swap_used = max(0, swap_total - info.get("SwapFree", 0))
        used = max(0, total - available)
        return {
            "total_bytes": total,
            "used_bytes": used,
            "available_bytes": available,
            "usage_percent": round(100 * used / total, 2) if total else 0.0,
            "cached_bytes": info.get("Cached"),
            "buffers_bytes": info.get("Buffers"),
            "swap_total_bytes": swap_total,
            "swap_used_bytes": swap_used,
            "swap_percent": round(100 * swap_used / swap_total, 2) if swap_total else 0.0,
        }
