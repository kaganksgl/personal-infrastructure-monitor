"""Single source of truth for the scalar metrics InfraWatch stores.

Each entry corresponds to a column on ``MetricSample`` and may be queried
through the history API, rolled up by the retention job, and used in alert
rules. Keeping the list here (instead of scattering string literals) means
adding a metric is: add a column + migration, then add one line below.
"""

from dataclasses import dataclass
from enum import StrEnum


class Unit(StrEnum):
    PERCENT = "percent"
    BYTES = "bytes"
    BYTES_PER_SEC = "bytes_per_sec"
    PER_SEC = "per_sec"
    CELSIUS = "celsius"
    LOAD = "load"


@dataclass(frozen=True, slots=True)
class MetricDef:
    name: str
    label: str
    unit: Unit


METRICS: dict[str, MetricDef] = {
    m.name: m
    for m in (
        MetricDef("cpu_percent", "CPU usage", Unit.PERCENT),
        MetricDef("load_1m", "Load average (1m)", Unit.LOAD),
        MetricDef("load_5m", "Load average (5m)", Unit.LOAD),
        MetricDef("load_15m", "Load average (15m)", Unit.LOAD),
        MetricDef("memory_percent", "Memory usage", Unit.PERCENT),
        MetricDef("memory_used_bytes", "Memory used", Unit.BYTES),
        MetricDef("swap_percent", "Swap usage", Unit.PERCENT),
        MetricDef("disk_percent_max", "Fullest filesystem", Unit.PERCENT),
        MetricDef("disk_read_bps", "Disk read", Unit.BYTES_PER_SEC),
        MetricDef("disk_write_bps", "Disk write", Unit.BYTES_PER_SEC),
        MetricDef("net_rx_bps", "Network RX", Unit.BYTES_PER_SEC),
        MetricDef("net_tx_bps", "Network TX", Unit.BYTES_PER_SEC),
        MetricDef("net_rx_pps", "Packets RX", Unit.PER_SEC),
        MetricDef("net_tx_pps", "Packets TX", Unit.PER_SEC),
        MetricDef("net_errors_ps", "Network errors", Unit.PER_SEC),
        MetricDef("net_drops_ps", "Dropped packets", Unit.PER_SEC),
        MetricDef("temperature_max_c", "Hottest sensor", Unit.CELSIUS),
    )
}

METRIC_NAMES: tuple[str, ...] = tuple(METRICS)
