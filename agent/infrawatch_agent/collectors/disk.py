"""Filesystem capacity (statvfs via psutil) and block-device I/O (/proc/diskstats)."""

import time
from typing import Any

import psutil

from infrawatch_agent.collectors.base import HostPaths, read_text
from infrawatch_agent.collectors.rates import CounterRates

# /proc/diskstats always counts in 512-byte sectors, regardless of the
# device's real sector size.
SECTOR_BYTES = 512
_IGNORED_FSTYPES = frozenset({"squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660", "ramfs"})


class DiskCollector:
    name = "disks"

    def __init__(self, paths: HostPaths) -> None:
        self._paths = paths
        self._rates = CounterRates()

    def prime(self) -> None:
        self._io(time.monotonic())

    def collect(self) -> dict[str, Any]:
        return {"filesystems": self._filesystems(), "io": self._io(time.monotonic())}

    def _filesystems(self) -> list[dict[str, Any]]:
        result = []
        seen_devices: set[str] = set()
        for part in psutil.disk_partitions(all=False):
            # Btrfs subvolumes and bind mounts expose the same device several
            # times with identical usage; report each device once.
            if part.fstype in _IGNORED_FSTYPES or part.device in seen_devices:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue  # e.g. an unmounted network share or a root-only mount
            seen_devices.add(part.device)
            result.append(
                {
                    "mountpoint": part.mountpoint[:256],
                    "device": part.device[:256],
                    "fstype": part.fstype[:64],
                    "total_bytes": usage.total,
                    "used_bytes": usage.used,
                    "free_bytes": usage.free,
                    "usage_percent": round(usage.percent, 2),
                }
            )
        return result[:64]

    def _physical_devices(self) -> set[str] | None:
        """Whole physical disks: entries in /sys/block that have a ``device`` link.

        This excludes partitions (avoids double counting), loop/ram/zram and
        device-mapper/md virtual devices that sit on top of physical disks.
        """
        block = self._paths.sys / "block"
        try:
            return {d.name for d in block.iterdir() if (d / "device").exists()}
        except OSError:
            return None

    def _io(self, now: float) -> list[dict[str, Any]]:
        physical = self._physical_devices()
        devices = []
        for line in (read_text(self._paths.proc / "diskstats") or "").splitlines():
            fields = line.split()
            if len(fields) < 14:
                continue
            name = fields[2]
            if physical is not None and name not in physical:
                continue
            reads, sectors_read = int(fields[3]), int(fields[5])
            writes, sectors_written = int(fields[7]), int(fields[9])
            io_ms = int(fields[12])
            busy = self._rates.rate(f"{name}:busy", io_ms, now) / 10  # ms per s -> %
            devices.append(
                {
                    "device": name,
                    "read_bytes_per_sec": round(
                        self._rates.rate(f"{name}:rb", sectors_read * SECTOR_BYTES, now), 1
                    ),
                    "write_bytes_per_sec": round(
                        self._rates.rate(f"{name}:wb", sectors_written * SECTOR_BYTES, now), 1
                    ),
                    "read_ops_per_sec": round(self._rates.rate(f"{name}:r", reads, now), 2),
                    "write_ops_per_sec": round(self._rates.rate(f"{name}:w", writes, now), 2),
                    "busy_percent": round(min(100.0, busy), 1),
                }
            )
        self._rates.forget_except(f"{d['device']}:" for d in devices)
        return devices[:128]
