"""Builders for realistic agent payloads."""

from datetime import UTC, datetime, timedelta
from typing import Any


def make_sample(
    agent_id: str,
    ts: datetime | None = None,
    *,
    cpu: float = 25.0,
    memory: float = 40.0,
    disk: float = 50.0,
    temp: float | None = 55.0,
    rx_bps: float = 1000.0,
    errors_ps: float = 0.0,
) -> dict[str, Any]:
    ts = ts or datetime.now(UTC)
    sensors = (
        [{"chip": "coretemp", "label": "Package id 0", "kind": "cpu", "current_c": temp}]
        if temp is not None
        else []
    )
    return {
        "schema_version": 1,
        "agent_id": agent_id,
        "timestamp": ts.isoformat(),
        "interval_seconds": 5,
        "cpu": {
            "usage_percent": cpu,
            "per_core_percent": [cpu, cpu],
            "logical_cores": 2,
            "physical_cores": 1,
            "frequency_mhz": 2400,
            "load_1m": 0.5,
            "load_5m": 0.4,
            "load_15m": 0.3,
        },
        "memory": {
            "total_bytes": 16 * 1024**3,
            "used_bytes": int(16 * 1024**3 * memory / 100),
            "available_bytes": int(16 * 1024**3 * (1 - memory / 100)),
            "usage_percent": memory,
            "swap_total_bytes": 0,
            "swap_used_bytes": 0,
            "swap_percent": 0,
        },
        "disks": {
            "filesystems": [
                {
                    "mountpoint": "/",
                    "device": "/dev/nvme0n1p2",
                    "fstype": "ext4",
                    "total_bytes": 100,
                    "used_bytes": int(disk),
                    "free_bytes": 100 - int(disk),
                    "usage_percent": disk,
                }
            ],
            "io": [
                {
                    "device": "nvme0n1",
                    "read_bytes_per_sec": 100.0,
                    "write_bytes_per_sec": 200.0,
                    "read_ops_per_sec": 1.0,
                    "write_ops_per_sec": 2.0,
                }
            ],
        },
        "network": {
            "interfaces": [
                {
                    "name": "eth0",
                    "is_up": True,
                    "rx_bytes": 10_000,
                    "tx_bytes": 5_000,
                    "rx_packets": 100,
                    "tx_packets": 50,
                    "rx_bytes_per_sec": rx_bps,
                    "tx_bytes_per_sec": rx_bps / 2,
                    "errors_per_sec": errors_ps,
                }
            ],
            "tcp_states": {"ESTABLISHED": 12, "LISTEN": 4},
        },
        "sensors": {"temperatures": sensors},
        "processes": {
            "total": 321,
            "top_cpu": [
                {
                    "pid": 1,
                    "name": "systemd",
                    "username": "root",
                    "cpu_percent": 0.1,
                    "memory_percent": 0.2,
                    "memory_rss_bytes": 1000,
                    "status": "sleeping",
                }
            ],
            "top_memory": [],
        },
        "host": {
            "uptime_seconds": 3600,
            "boot_time": (ts - timedelta(hours=1)).isoformat(),
        },
        "agent": {
            "version": "1.0.0",
            "cpu_percent": 0.5,
            "memory_rss_bytes": 30_000_000,
            "collection_duration_ms": 12.5,
            "queue_size": 0,
            "failed_requests_total": 0,
        },
    }


def system_info() -> dict[str, Any]:
    return {
        "hostname": "test-host",
        "os_name": "Fedora Linux",
        "os_version": "43",
        "kernel": "6.12.0",
        "architecture": "x86_64",
        "cpu_model": "Test CPU",
        "cpu_physical_cores": 1,
        "cpu_logical_cores": 2,
        "memory_total_bytes": 16 * 1024**3,
        "boot_time": datetime.now(UTC).isoformat(),
        "agent_version": "1.0.0",
    }
