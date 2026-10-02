"""Uptime and boot time (dynamic) and static system information."""

import platform
import socket
from datetime import datetime, timezone
from typing import Any

import psutil

from infrawatch_agent import __version__
from infrawatch_agent.collectors.base import HostPaths, read_text


def boot_time(paths: HostPaths) -> datetime:
    for line in (read_text(paths.proc / "stat") or "").splitlines():
        if line.startswith("btime "):
            return datetime.fromtimestamp(int(line.split()[1]), timezone.utc)
    return datetime.fromtimestamp(psutil.boot_time(), timezone.utc)


def uptime_seconds(paths: HostPaths) -> float:
    text = read_text(paths.proc / "uptime")
    return float(text.split()[0]) if text else 0.0


class HostCollector:
    name = "host"

    def __init__(self, paths: HostPaths) -> None:
        self._paths = paths

    def prime(self) -> None:
        pass

    def collect(self) -> dict[str, Any]:
        return {
            "uptime_seconds": uptime_seconds(self._paths),
            "boot_time": boot_time(self._paths).isoformat(),
        }


def parse_os_release(text: str) -> dict[str, str]:
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip().strip('"')
    return values


def cpu_model(paths: HostPaths) -> str | None:
    for line in (read_text(paths.proc / "cpuinfo") or "").splitlines():
        key, _, value = line.partition(":")
        # x86 uses "model name"; many ARM kernels use "Model" or "Hardware".
        if key.strip() in ("model name", "Model", "Hardware") and value.strip():
            return value.strip()[:256]
    return platform.processor() or None


def system_info(paths: HostPaths) -> dict[str, Any]:
    os_release = parse_os_release(
        read_text(paths.etc / "os-release")
        or read_text(paths.etc / ".." / "usr/lib/os-release")
        or ""
    )
    uname = platform.uname()
    return {
        "hostname": socket.gethostname()[:64],
        "os_name": os_release.get("PRETTY_NAME") or os_release.get("NAME") or uname.system,
        "os_version": os_release.get("VERSION_ID"),
        "kernel": uname.release[:64],
        "architecture": uname.machine[:64],
        "cpu_model": cpu_model(paths),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True) or 1,
        "memory_total_bytes": psutil.virtual_memory().total,
        "boot_time": boot_time(paths).isoformat(),
        "agent_version": __version__,
        "runtime": f"Python {platform.python_version()}",
    }
