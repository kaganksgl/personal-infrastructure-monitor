"""Top processes by CPU and memory.

psutil is used here because a portable, race-safe process walk is genuinely
fiddly (/proc/<pid>/stat parsing, UID->name lookup, kernel threads, PID
reuse). ``process_iter`` caches ``Process`` objects between calls, which is
what makes per-process ``cpu_percent`` meaningful across collection cycles.

Processes routinely exit mid-scan and some fields of other users' processes
are unreadable without root; both are expected and handled per process.
"""

import heapq
from typing import Any

import psutil

from infrawatch_agent.security.redact import redact_cmdline

_ATTRS = ["pid", "name", "username", "status", "cpu_percent", "memory_percent", "memory_info",
          "num_threads"]  # fmt: skip
_GONE = (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied)


class ProcessCollector:
    name = "processes"

    def __init__(self, top_n: int = 10, cmdline: bool = True) -> None:
        self._top_n = top_n
        self._cmdline = cmdline

    def prime(self) -> None:
        # The first cpu_percent() call per process only records a baseline.
        for _ in psutil.process_iter(["cpu_percent"]):
            pass

    def collect(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        running = 0
        for proc in psutil.process_iter(_ATTRS, ad_value=None):
            info = proc.info
            if info.get("status") == psutil.STATUS_RUNNING:
                running += 1
            mem = info.get("memory_info")
            rows.append(
                {
                    "pid": info["pid"],
                    "name": (info.get("name") or "?")[:128],
                    "username": (info.get("username") or None) and info["username"][:64],
                    "cpu_percent": round(info.get("cpu_percent") or 0.0, 1),
                    "memory_percent": round(min(100.0, info.get("memory_percent") or 0.0), 2),
                    "memory_rss_bytes": mem.rss if mem else 0,
                    "status": (info.get("status") or "unknown")[:64],
                    "num_threads": info.get("num_threads"),
                    "_proc": proc,
                }
            )
        top_cpu = heapq.nlargest(self._top_n, rows, key=lambda r: r["cpu_percent"])
        top_mem = heapq.nlargest(self._top_n, rows, key=lambda r: r["memory_rss_bytes"])
        return {
            "total": len(rows),
            "running": running,
            "top_cpu": [self._finish(r) for r in top_cpu],
            "top_memory": [self._finish(r) for r in top_mem],
        }

    def _finish(self, row: dict[str, Any]) -> dict[str, Any]:
        """Strip the internal handle and (only for the few top rows) add the command line."""
        out = {k: v for k, v in row.items() if k != "_proc"}
        out["cmdline"] = None
        if self._cmdline:
            try:
                args = row["_proc"].cmdline()
                out["cmdline"] = redact_cmdline(" ".join(args))[:512] if args else None
            except _GONE:
                pass
        return out
