"""CPU utilisation from /proc/stat jiffy counters.

The kernel exposes cumulative time (in USER_HZ ticks) each CPU has spent in
each state since boot. Utilisation over an interval is therefore

    busy% = Δ(total - idle - iowait) / Δtotal * 100

which is exactly what ``top`` does. ``guest`` time is already included in
``user`` so it is not added again.
"""

import time
from dataclasses import dataclass
from typing import Any

import psutil

from infrawatch_agent.collectors.base import HostPaths, read_text
from infrawatch_agent.collectors.rates import CounterRates


@dataclass(frozen=True)
class CpuTimes:
    total: int
    idle: int
    iowait: int
    steal: int

    @classmethod
    def parse(cls, fields: list[str]) -> "CpuTimes":
        values = [int(v) for v in fields[:8]] + [0] * (8 - len(fields[:8]))
        user, nice, system, idle, iowait, irq, softirq, steal = values
        return cls(
            total=user + nice + system + idle + iowait + irq + softirq + steal,
            idle=idle,
            iowait=iowait,
            steal=steal,
        )


def _percent(part: int, total: int) -> float:
    return round(min(100.0, max(0.0, 100.0 * part / total)), 2) if total > 0 else 0.0


class CpuCollector:
    name = "cpu"

    def __init__(self, paths: HostPaths) -> None:
        self._paths = paths
        self._previous: dict[str, CpuTimes] = {}
        self._rates = CounterRates()

    def _read_stat(self) -> tuple[dict[str, CpuTimes], dict[str, int]]:
        cpus: dict[str, CpuTimes] = {}
        counters: dict[str, int] = {}
        for line in (read_text(self._paths.proc / "stat") or "").splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0].startswith("cpu"):
                cpus[parts[0]] = CpuTimes.parse(parts[1:])
            elif parts[0] in ("ctxt", "intr"):
                counters[parts[0]] = int(parts[1])
        if "cpu" not in cpus:
            raise RuntimeError("/proc/stat has no aggregate cpu line")
        return cpus, counters

    def prime(self) -> None:
        cpus, counters = self._read_stat()
        self._previous = cpus
        now = time.monotonic()
        for key, value in counters.items():
            self._rates.rate(key, value, now)

    def _usage(self, key: str, current: CpuTimes) -> tuple[float, float, float]:
        previous = self._previous.get(key)
        if previous is None:
            return 0.0, 0.0, 0.0
        d_total = current.total - previous.total
        d_idle = (current.idle - previous.idle) + (current.iowait - previous.iowait)
        return (
            _percent(d_total - d_idle, d_total),
            _percent(current.iowait - previous.iowait, d_total),
            _percent(current.steal - previous.steal, d_total),
        )

    def _load_average(self) -> tuple[float, float, float]:
        text = read_text(self._paths.proc / "loadavg") or "0 0 0"
        one, five, fifteen = (float(x) for x in text.split()[:3])
        return one, five, fifteen

    def collect(self) -> dict[str, Any]:
        cpus, counters = self._read_stat()
        now = time.monotonic()
        usage, iowait, steal = self._usage("cpu", cpus["cpu"])
        cores = sorted((k for k in cpus if k != "cpu"), key=lambda k: int(k[3:]))
        per_core = [self._usage(k, cpus[k])[0] for k in cores]
        self._previous = cpus
        load_1, load_5, load_15 = self._load_average()

        frequency = None
        try:
            freq = psutil.cpu_freq()
            frequency = round(freq.current, 1) if freq else None
        except (OSError, NotImplementedError):
            pass  # not exposed in many VMs/containers

        return {
            "usage_percent": usage,
            "per_core_percent": per_core,
            "logical_cores": max(1, len(cores)),
            "physical_cores": psutil.cpu_count(logical=False),
            "frequency_mhz": frequency,
            "load_1m": load_1,
            "load_5m": load_5,
            "load_15m": load_15,
            "iowait_percent": iowait,
            "steal_percent": steal,
            "context_switches_per_sec": round(self._rates.rate("ctxt", counters["ctxt"], now), 1)
            if "ctxt" in counters
            else None,
            "interrupts_per_sec": round(self._rates.rate("intr", counters["intr"], now), 1)
            if "intr" in counters
            else None,
        }
