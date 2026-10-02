"""Per-interface network statistics.

Counters come from /proc/net/dev; link state, speed and MTU from
/sys/class/net/<iface>/. TCP connection states are counted from
/proc/net/tcp and /proc/net/tcp6, where column 4 (``st``) holds the state as
a hex code defined in include/net/tcp_states.h.
"""

import re
import socket
import time
from typing import Any

import psutil

from infrawatch_agent.collectors.base import HostPaths, read_int, read_text
from infrawatch_agent.collectors.rates import CounterRates

TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}

# /proc/net/dev receive columns, then transmit columns (see `man 5 proc`).
_RX_FIELDS = ("bytes", "packets", "errs", "drop", "fifo", "frame", "compressed", "multicast")
_TX_FIELDS = ("bytes", "packets", "errs", "drop", "fifo", "colls", "carrier", "compressed")


def parse_net_dev(text: str) -> dict[str, dict[str, int]]:
    interfaces: dict[str, dict[str, int]] = {}
    for line in text.splitlines()[2:]:  # two header lines
        name, sep, data = line.partition(":")
        if not sep:
            continue
        values = [int(v) for v in data.split()]
        stats = {f"rx_{k}": v for k, v in zip(_RX_FIELDS, values[:8], strict=False)}
        stats |= {f"tx_{k}": v for k, v in zip(_TX_FIELDS, values[8:16], strict=False)}
        interfaces[name.strip()] = stats
    return interfaces


def count_tcp_states(*tables: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        for line in table.splitlines()[1:]:
            fields = line.split()
            if len(fields) > 3:
                state = TCP_STATES.get(fields[3].upper(), "UNKNOWN")
                counts[state] = counts.get(state, 0) + 1
    return counts


class NetworkCollector:
    name = "network"

    def __init__(self, paths: HostPaths, exclude: str = r"^lo$") -> None:
        self._paths = paths
        self._exclude = re.compile(exclude)
        self._rates = CounterRates()

    def prime(self) -> None:
        self._interfaces(time.monotonic())

    def collect(self) -> dict[str, Any]:
        return {"interfaces": self._interfaces(time.monotonic()), "tcp_states": self._tcp_states()}

    def _link_info(self, name: str) -> dict[str, Any]:
        base = self._paths.sys / "class" / "net" / name
        operstate = read_text(base / "operstate", "unknown")
        speed = read_int(base / "speed")  # Mb/s; -1 or unreadable for wireless/virtual links
        return {
            # "unknown" is common for virtual links (tun, wireguard) that are in fact up.
            "is_up": operstate in ("up", "unknown") and read_int(base / "carrier") != 0,
            "speed_mbps": speed if speed and speed > 0 else None,
            "mtu": read_int(base / "mtu"),
        }

    @staticmethod
    def _addresses() -> dict[str, list[str]]:
        try:
            addrs = psutil.net_if_addrs()
        except OSError:
            return {}
        families = (socket.AF_INET, socket.AF_INET6)
        return {
            name: [a.address.split("%")[0][:64] for a in entries if a.family in families][:16]
            for name, entries in addrs.items()
        }

    def _interfaces(self, now: float) -> list[dict[str, Any]]:
        counters = parse_net_dev(read_text(self._paths.proc / "net" / "dev") or "")
        addresses = self._addresses()
        result = []
        for name, c in sorted(counters.items()):
            if self._exclude.match(name):
                continue

            def r(field: str, name: str = name, c: dict[str, int] = c) -> float:
                return self._rates.rate(f"{name}:{field}", c[field], now)

            result.append(
                {
                    "name": name[:64],
                    **self._link_info(name),
                    "addresses": addresses.get(name, []),
                    "rx_bytes": c["rx_bytes"],
                    "tx_bytes": c["tx_bytes"],
                    "rx_packets": c["rx_packets"],
                    "tx_packets": c["tx_packets"],
                    "rx_errors": c["rx_errs"],
                    "tx_errors": c["tx_errs"],
                    "rx_dropped": c["rx_drop"],
                    "tx_dropped": c["tx_drop"],
                    "rx_bytes_per_sec": round(r("rx_bytes"), 1),
                    "tx_bytes_per_sec": round(r("tx_bytes"), 1),
                    "rx_packets_per_sec": round(r("rx_packets"), 2),
                    "tx_packets_per_sec": round(r("tx_packets"), 2),
                    "errors_per_sec": round(r("rx_errs") + r("tx_errs"), 3),
                    "drops_per_sec": round(r("rx_drop") + r("tx_drop"), 3),
                }
            )
        self._rates.forget_except(f"{i['name']}:" for i in result)
        return result[:128]

    def _tcp_states(self) -> dict[str, int] | None:
        tables = [read_text(self._paths.proc / "net" / t) for t in ("tcp", "tcp6")]
        present = [t for t in tables if t is not None]
        return count_tcp_states(*present) if present else None
