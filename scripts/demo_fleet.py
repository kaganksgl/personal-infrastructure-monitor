#!/usr/bin/env python3
"""Simulate a small fleet of machines for demos, screenshots and load tests.

Registers synthetic agents through the admin API, optionally backfills
history, then streams samples over the real agent protocol (same endpoints and
authentication as the actual agent). Credentials come from the environment:

    INFRAWATCH_USER=admin INFRAWATCH_PASSWORD=... \\
        python scripts/demo_fleet.py --server http://localhost:8080 --backfill-minutes 120

One host ("build-runner") periodically saturates its CPU so alerts fire.
"""

import argparse
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

HOSTS = [
    ("web-01", "Web server", "Ubuntu 24.04.1 LTS", 4, 8),
    ("db-01", "PostgreSQL primary", "Debian GNU/Linux 12 (bookworm)", 8, 32),
    ("build-runner", "CI build runner", "Fedora Linux 43", 16, 64),
    ("pi-homelab", "Raspberry Pi 5", "Debian GNU/Linux 12 (bookworm)", 4, 8),
]
GIB = 1024**3


@dataclass
class SimHost:
    agent_id: str
    name: str
    os_name: str
    cores: int
    mem_gib: int
    key: str = ""
    boot: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=random.randint(1, 40)))
    rx_total: int = 0
    tx_total: int = 0

    def sample(self, ts: datetime) -> dict[str, Any]:
        minute = ts.timestamp() / 60
        busy = self.agent_id == "build-runner" and int(minute) % 12 < 3
        cpu = 96 + random.random() * 3 if busy else max(1.0, 18 + 12 * math.sin(minute / 7) + random.gauss(0, 4))
        mem = min(97.0, 35 + 10 * math.sin(minute / 30) + random.gauss(0, 1) + (25 if busy else 0))
        rx = max(0.0, 250_000 + 200_000 * math.sin(minute / 3) + random.expovariate(1 / 150_000))
        tx = max(0.0, rx * 0.35 + random.gauss(0, 20_000))
        self.rx_total += int(rx * 5)
        self.tx_total += int(tx * 5)
        temp = 45 + cpu * 0.35 + random.gauss(0, 1)
        used = int(self.mem_gib * GIB * mem / 100)
        load = self.cores * cpu / 100
        return {
            "schema_version": 1,
            "agent_id": self.agent_id,
            "timestamp": ts.isoformat(),
            "interval_seconds": 5,
            "cpu": {
                "usage_percent": round(cpu, 2),
                "per_core_percent": [round(min(100, max(0, cpu + random.gauss(0, 8))), 1) for _ in range(self.cores)],
                "logical_cores": self.cores,
                "physical_cores": max(1, self.cores // 2),
                "frequency_mhz": 2400 + random.random() * 1200,
                "load_1m": round(load, 2),
                "load_5m": round(load * 0.9, 2),
                "load_15m": round(load * 0.8, 2),
                "iowait_percent": round(random.random() * 2, 2),
                "steal_percent": 0.0,
                "context_switches_per_sec": 8000 + random.random() * 4000,
                "interrupts_per_sec": 4000 + random.random() * 2000,
            },
            "memory": {
                "total_bytes": self.mem_gib * GIB,
                "used_bytes": used,
                "available_bytes": self.mem_gib * GIB - used,
                "usage_percent": round(mem, 2),
                "cached_bytes": GIB,
                "buffers_bytes": GIB // 8,
                "swap_total_bytes": 2 * GIB,
                "swap_used_bytes": GIB // 10,
                "swap_percent": 5.0,
            },
            "disks": {
                "filesystems": [
                    {"mountpoint": "/", "device": "/dev/nvme0n1p2", "fstype": "ext4", "total_bytes": 500 * GIB,
                     "used_bytes": 210 * GIB, "free_bytes": 290 * GIB, "usage_percent": 42.0},
                    {"mountpoint": "/var/lib/data", "device": "/dev/sda1", "fstype": "xfs", "total_bytes": 2000 * GIB,
                     "used_bytes": 1500 * GIB if self.agent_id == "db-01" else 400 * GIB,
                     "free_bytes": 500 * GIB, "usage_percent": 75.0 if self.agent_id == "db-01" else 20.0},
                ],
                "io": [{"device": "nvme0n1", "read_bytes_per_sec": random.expovariate(1 / 2e6),
                        "write_bytes_per_sec": random.expovariate(1 / 4e6), "read_ops_per_sec": random.random() * 80,
                        "write_ops_per_sec": random.random() * 150, "busy_percent": random.random() * 15}],
            },
            "network": {
                "interfaces": [
                    {"name": "eth0", "is_up": True, "speed_mbps": 1000, "mtu": 1500,
                     "addresses": ["192.0.2." + str(10 + HOSTS.index(next(h for h in HOSTS if h[0] == self.agent_id)))],
                     "rx_bytes": self.rx_total, "tx_bytes": self.tx_total,
                     "rx_packets": self.rx_total // 900, "tx_packets": self.tx_total // 700,
                     "rx_bytes_per_sec": rx, "tx_bytes_per_sec": tx,
                     "rx_packets_per_sec": rx / 900, "tx_packets_per_sec": tx / 700,
                     "errors_per_sec": 0.0, "drops_per_sec": random.choice([0.0] * 20 + [0.2])},
                ],
                "tcp_states": {"ESTABLISHED": random.randint(20, 80), "LISTEN": 6, "TIME_WAIT": random.randint(0, 30)},
            },
            "sensors": {"temperatures": [] if self.agent_id == "web-01" else [
                {"chip": "coretemp", "label": "Package id 0", "kind": "cpu", "current_c": round(temp, 1),
                 "high_c": 90.0, "critical_c": 100.0},
                {"chip": "nvme", "label": "Composite", "kind": "nvme", "current_c": round(38 + random.random() * 4, 1)},
            ]},
            "processes": {
                "total": 180 + random.randint(0, 40),
                "running": random.randint(1, 4),
                "top_cpu": [{"pid": 4242, "name": "cc1plus" if busy else "nginx", "username": "builder" if busy else "www-data",
                             "cpu_percent": round(cpu * self.cores / 3, 1), "memory_percent": 2.1,
                             "memory_rss_bytes": 300_000_000, "status": "running", "num_threads": 1,
                             "cmdline": "cc1plus -O2 main.cpp" if busy else "nginx: worker process"}],
                "top_memory": [{"pid": 1200, "name": "postgres", "username": "postgres", "cpu_percent": 3.2,
                                "memory_percent": 12.5, "memory_rss_bytes": 2 * GIB, "status": "sleeping",
                                "num_threads": 1, "cmdline": "postgres: checkpointer"}],
            },
            "host": {"uptime_seconds": (ts - self.boot).total_seconds(), "boot_time": self.boot.isoformat()},
            "agent": {"version": "1.0.0", "cpu_percent": 0.4, "memory_rss_bytes": 38_000_000,
                      "collection_duration_ms": 35.0, "queue_size": 0, "failed_requests_total": 0},
        }  # fmt: skip

    def system_info(self) -> dict[str, Any]:
        return {
            "hostname": self.agent_id, "os_name": self.os_name, "os_version": None, "kernel": "6.8.0-45-generic",
            "architecture": "aarch64" if "pi" in self.agent_id else "x86_64",
            "cpu_model": "Cortex-A76" if "pi" in self.agent_id else "AMD EPYC 7B13",
            "cpu_physical_cores": max(1, self.cores // 2), "cpu_logical_cores": self.cores,
            "memory_total_bytes": self.mem_gib * GIB, "boot_time": self.boot.isoformat(),
            "agent_version": "1.0.0", "runtime": "simulated",
        }  # fmt: skip


def register(client: httpx.Client, hosts: list[SimHost]) -> None:
    existing = {a["agent_id"] for a in client.get("/api/v1/agents").raise_for_status().json()}
    for host in hosts:
        path = f"/api/v1/agents/{host.agent_id}/rotate-key" if host.agent_id in existing else "/api/v1/agents"
        body = None if host.agent_id in existing else {"agent_id": host.agent_id, "display_name": host.name}
        host.key = client.post(path, json=body).raise_for_status().json()["api_key"]


def send(server: str, host: SimHost, samples: list[dict[str, Any]], with_info: bool) -> None:
    payload: dict[str, Any] = {"agent_id": host.agent_id, "samples": samples}
    if with_info:
        payload["system_info"] = host.system_info()
    headers = {"Authorization": f"Bearer {host.key}", "X-Agent-ID": host.agent_id}
    httpx.post(f"{server}/api/v1/metrics/batch", json=payload, headers=headers, timeout=10).raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default="http://localhost:8080")
    parser.add_argument("--backfill-minutes", type=int, default=0)
    parser.add_argument("--duration", type=int, default=0, help="seconds to stream (0 = forever)")
    args = parser.parse_args()
    user, password = os.environ.get("INFRAWATCH_USER"), os.environ.get("INFRAWATCH_PASSWORD")
    if not user or not password:
        print("Set INFRAWATCH_USER and INFRAWATCH_PASSWORD (an admin account).", file=sys.stderr)
        return 2

    hosts = [SimHost(*h) for h in HOSTS]
    with httpx.Client(base_url=args.server, headers={"X-Requested-With": "demo"}, timeout=10) as client:
        login = client.post("/api/v1/auth/login", json={"username": user, "password": password})
        login.raise_for_status()
        # The session cookie is Secure; browsers send it to http://localhost but
        # Python's cookie jar does not, so forward it explicitly.
        client.headers["Cookie"] = f"iw_session={login.cookies['iw_session']}"
        register(client, hosts)

    now = datetime.now(UTC)
    for host in hosts:
        steps = args.backfill_minutes * 12
        stamps = [now - timedelta(seconds=5 * i) for i in range(steps, 0, -1)]
        for i in range(0, len(stamps), 100):
            send(args.server, host, [host.sample(t) for t in stamps[i : i + 100]], with_info=i == 0)
        print(f"{host.agent_id}: backfilled {len(stamps)} samples")

    started = time.monotonic()
    while not args.duration or time.monotonic() - started < args.duration:
        for host in hosts:
            send(args.server, host, [host.sample(datetime.now(UTC))], with_info=True)
        time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
