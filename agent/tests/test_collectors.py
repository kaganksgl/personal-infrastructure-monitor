from pathlib import Path
from typing import ClassVar

import psutil
import pytest

from infrawatch_agent.collectors import CollectorRegistry, HostPaths
from infrawatch_agent.collectors.cpu import CpuCollector
from infrawatch_agent.collectors.disk import DiskCollector
from infrawatch_agent.collectors.host import HostCollector, system_info
from infrawatch_agent.collectors.memory import MemoryCollector
from infrawatch_agent.collectors.network import NetworkCollector
from infrawatch_agent.collectors.processes import ProcessCollector
from infrawatch_agent.collectors.sensors import SensorCollector
from tests.conftest import DISKSTATS, NET_DEV, PROC_STAT_2, write


def test_cpu_usage_from_jiffy_deltas(fake_host: HostPaths):
    cpu = CpuCollector(fake_host)
    cpu.prime()
    write(fake_host.proc / "stat", PROC_STAT_2)
    data = cpu.collect()
    assert data["usage_percent"] == pytest.approx(66.67, abs=0.01)
    assert data["iowait_percent"] == pytest.approx(16.67, abs=0.01)
    assert data["per_core_percent"] == pytest.approx([60.0, 71.43], abs=0.01)
    assert data["logical_cores"] == 2
    assert (data["load_1m"], data["load_5m"], data["load_15m"]) == (1.23, 1.12, 0.98)
    assert data["context_switches_per_sec"] > 0


def test_cpu_first_sample_without_baseline_is_zero_not_garbage(fake_host: HostPaths):
    assert CpuCollector(fake_host).collect()["usage_percent"] == 0.0


def test_memory_used_excludes_reclaimable_cache(fake_host: HostPaths):
    data = MemoryCollector(fake_host).collect()
    assert data["total_bytes"] == 16_000_000 * 1024
    assert data["usage_percent"] == 50.0
    assert data["swap_percent"] == 25.0
    assert data["cached_bytes"] == 4_000_000 * 1024


def test_network_rates_filters_and_link_state(fake_host: HostPaths, monkeypatch):
    clock = iter([100.0, 102.0])
    monkeypatch.setattr("infrawatch_agent.collectors.network.time.monotonic", lambda: next(clock))
    collector = NetworkCollector(fake_host, exclude=r"^(lo|veth.*)$")
    collector.prime()
    write(fake_host.proc / "net" / "dev", NET_DEV.format(rx=3_000_000, tx=600_000))
    data = collector.collect()
    (eth0,) = data["interfaces"]
    assert eth0["name"] == "eth0" and eth0["is_up"] and eth0["speed_mbps"] == 1000
    assert eth0["rx_bytes_per_sec"] == 1_000_000.0  # 2 MB over 2 s
    assert eth0["tx_bytes_per_sec"] == 50_000.0
    assert eth0["rx_errors"] == 2 and eth0["rx_dropped"] == 1
    assert data["tcp_states"] == {"LISTEN": 1, "ESTABLISHED": 1, "TIME_WAIT": 1}


def test_network_counter_reset_yields_zero_not_negative(fake_host: HostPaths):
    collector = NetworkCollector(fake_host)
    collector.prime()
    write(fake_host.proc / "net" / "dev", NET_DEV.format(rx=10, tx=10))
    eth0 = next(i for i in collector.collect()["interfaces"] if i["name"] == "eth0")
    assert eth0["rx_bytes_per_sec"] == 0.0


def test_disk_io_counts_only_physical_disks(fake_host: HostPaths, monkeypatch):
    clock = iter([10.0, 11.0, 11.0])
    monkeypatch.setattr("infrawatch_agent.collectors.disk.time.monotonic", lambda: next(clock))
    collector = DiskCollector(fake_host)
    collector.prime()
    write(fake_host.proc / "diskstats", DISKSTATS.format(r=110, rs=4000, w=60, ws=3000, io=250))
    data = collector.collect()
    (disk,) = data["io"]
    assert disk["device"] == "nvme0n1"
    assert disk["read_bytes_per_sec"] == 2000 * 512
    assert disk["write_ops_per_sec"] == 10
    assert disk["busy_percent"] == 25.0
    assert data["filesystems"], "real statvfs of this machine's mounts"


def test_missing_sensors_return_empty_list(fake_host: HostPaths):
    assert SensorCollector(fake_host).collect() == {"temperatures": []}


def test_hwmon_sensors_are_classified(fake_host: HostPaths):
    hwmon = fake_host.sys / "class" / "hwmon"
    write(hwmon / "hwmon0" / "name", "coretemp")
    write(hwmon / "hwmon0" / "temp1_input", "52000")
    write(hwmon / "hwmon0" / "temp1_label", "Package id 0")
    write(hwmon / "hwmon0" / "temp1_crit", "100000")
    write(hwmon / "hwmon1" / "name", "nvme")
    write(hwmon / "hwmon1" / "temp1_input", "41850")
    write(hwmon / "hwmon2" / "name", "broken")
    write(hwmon / "hwmon2" / "temp1_input", "-273000")  # implausible -> ignored
    temps = SensorCollector(fake_host).collect()["temperatures"]
    assert [(t["kind"], t["current_c"]) for t in temps] == [("cpu", 52.0), ("nvme", 41.9)]
    assert temps[0]["label"] == "Package id 0" and temps[0]["critical_c"] == 100.0


def test_thermal_zone_fallback(fake_host: HostPaths):
    zone = fake_host.sys / "class" / "thermal" / "thermal_zone0"
    write(zone / "temp", "47000")
    write(zone / "type", "x86_pkg_temp")
    (temp,) = SensorCollector(fake_host).collect()["temperatures"]
    assert temp["kind"] == "cpu" and temp["current_c"] == 47.0


def test_process_collector_on_real_system():
    collector = ProcessCollector(top_n=5)
    collector.prime()
    data = collector.collect()
    assert data["total"] > 0
    assert 0 < len(data["top_cpu"]) <= 5 and len(data["top_memory"]) <= 5
    first = data["top_memory"][0]
    assert {"pid", "name", "cpu_percent", "memory_percent", "status", "cmdline"} <= set(first)
    assert "_proc" not in first


def test_process_disappearing_mid_collection(monkeypatch):
    class Vanishing:
        info: ClassVar[dict] = {
            "pid": 999999,
            "name": "ghost",
            "status": "running",
            "cpu_percent": 99.0,
            "memory_percent": 1.0,
            "memory_info": None,
            "username": None,
            "num_threads": 1,
        }

        def cmdline(self):
            raise psutil.NoSuchProcess(999999)

    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: iter([Vanishing()]))
    data = ProcessCollector(top_n=3).collect()
    assert data["top_cpu"][0]["name"] == "ghost"
    assert data["top_cpu"][0]["cmdline"] is None


def test_host_and_system_info(fake_host: HostPaths):
    host = HostCollector(fake_host).collect()
    assert host["uptime_seconds"] == 3600.5
    assert host["boot_time"].startswith("2023-11-14T22:13:20")
    info = system_info(fake_host)
    assert info["os_name"] == "Fedora Linux 43" and info["os_version"] == "43"
    assert info["cpu_model"] == "Test CPU @ 3.0GHz"


def test_registry_isolates_failing_collector(fake_host: HostPaths, tmp_path: Path):
    class Broken:
        name = "broken"

        def prime(self):
            raise PermissionError("denied")

        def collect(self):
            raise PermissionError("denied")

    registry = CollectorRegistry([Broken(), MemoryCollector(fake_host)])
    registry.prime()
    result = registry.collect()
    assert result.errors == ["broken"]
    assert "memory" in result.sections
