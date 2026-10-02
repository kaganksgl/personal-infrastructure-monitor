from pathlib import Path

import pytest

from infrawatch_agent.collectors import HostPaths
from infrawatch_agent.config import AgentConfig

PROC_STAT_1 = """cpu  1000 0 500 8000 100 0 0 0 0 0
cpu0 500 0 250 4000 50 0 0 0 0 0
cpu1 500 0 250 4000 50 0 0 0 0 0
intr 50000 1 2 3
ctxt 100000
btime 1700000000
processes 1234
"""
# 400 busy jiffies + 100 idle + 100 iowait over the interval (600 total).
PROC_STAT_2 = """cpu  1300 0 600 8100 200 0 0 0 0 0
cpu0 600 0 300 4050 100 0 0 0 0 0
cpu1 700 0 300 4050 100 0 0 0 0 0
intr 51000 1 2 3
ctxt 102000
btime 1700000000
processes 1240
"""
MEMINFO = """MemTotal:       16000000 kB
MemFree:         2000000 kB
MemAvailable:    8000000 kB
Buffers:          500000 kB
Cached:          4000000 kB
SwapTotal:       2000000 kB
SwapFree:        1500000 kB
"""
NET_DEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 5000 50 0 0 0 0 0 0 5000 50 0 0 0 0 0 0
  eth0: {rx} 1000 2 1 0 0 0 0 {tx} 800 0 0 0 0 0 0
vethabc: 999 9 0 0 0 0 0 0 999 9 0 0 0 0 0 0
"""
DISKSTATS = """ 259 0 nvme0n1 {r} 0 {rs} 0 {w} 0 {ws} 0 0 {io} 0
 259 1 nvme0n1p1 100 0 2000 0 50 0 1000 0 0 50 0
   7 0 loop0 10 0 20 0 0 0 0 0 0 1 0
"""
TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1
   1: 0100007F:1F90 0100007F:D431 01 00000000:00000000 00:00000000 00000000  1000        0 2
   2: 0100007F:1F90 0100007F:D432 06 00000000:00000000 00:00000000 00000000  1000        0 3
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def fake_host(tmp_path: Path) -> HostPaths:
    paths = HostPaths(proc=tmp_path / "proc", sys=tmp_path / "sys", etc=tmp_path / "etc")
    write(paths.proc / "stat", PROC_STAT_1)
    write(paths.proc / "loadavg", "1.23 1.12 0.98 2/500 12345")
    write(paths.proc / "meminfo", MEMINFO)
    write(paths.proc / "uptime", "3600.50 7000.00")
    write(paths.proc / "net" / "dev", NET_DEV.format(rx=1_000_000, tx=500_000))
    write(paths.proc / "net" / "tcp", TCP)
    write(paths.proc / "diskstats", DISKSTATS.format(r=100, rs=2000, w=50, ws=1000, io=0))
    write(paths.proc / "cpuinfo", "processor\t: 0\nmodel name\t: Test CPU @ 3.0GHz\n")
    write(
        paths.etc / "os-release",
        'NAME="Fedora Linux"\nVERSION_ID=43\nPRETTY_NAME="Fedora Linux 43"\n',
    )
    net = paths.sys / "class" / "net" / "eth0"
    write(net / "operstate", "up")
    write(net / "carrier", "1")
    write(net / "speed", "1000")
    write(net / "mtu", "1500")
    (paths.sys / "block" / "nvme0n1" / "device").mkdir(parents=True)
    (paths.sys / "block" / "loop0").mkdir(parents=True)
    return paths


@pytest.fixture
def config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(
        server_url="http://testserver",
        agent_id="test-agent",
        api_key="iwk_test",
        buffer_path=tmp_path / "buffer.db",
        state_path=tmp_path / "state.json",
        collection_interval=5,
    )
