"""Agent wire protocol, version 1.

These models define the JSON contract between agents and the backend. Any
agent implementation (Python today, Rust tomorrow) only has to produce this
shape; see docs/agent-protocol.md.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from app.schemas.common import (
    AgentId,
    ApiModel,
    Counter,
    MediumStr,
    NonNegFloat,
    NonNegInt,
    Percent,
    ShortStr,
    WireModel,
)

Celsius = Annotated[float, Field(ge=-60, le=250)]


class CpuMetrics(WireModel):
    usage_percent: Percent
    per_core_percent: list[Percent] = Field(default_factory=list, max_length=1024)
    logical_cores: int = Field(ge=1, le=4096)
    physical_cores: int | None = Field(default=None, ge=1, le=4096)
    frequency_mhz: NonNegFloat | None = None
    load_1m: NonNegFloat
    load_5m: NonNegFloat
    load_15m: NonNegFloat
    iowait_percent: Percent | None = None
    steal_percent: Percent | None = None
    context_switches_per_sec: NonNegFloat | None = None
    interrupts_per_sec: NonNegFloat | None = None


class MemoryMetrics(WireModel):
    total_bytes: Counter
    used_bytes: Counter
    available_bytes: Counter
    usage_percent: Percent
    cached_bytes: Counter | None = None
    buffers_bytes: Counter | None = None
    swap_total_bytes: Counter = 0
    swap_used_bytes: Counter = 0
    swap_percent: Percent = 0


class FilesystemUsage(WireModel):
    mountpoint: MediumStr
    device: MediumStr
    fstype: ShortStr
    total_bytes: Counter
    used_bytes: Counter
    free_bytes: Counter
    usage_percent: Percent


class DiskIO(WireModel):
    device: ShortStr
    read_bytes_per_sec: NonNegFloat
    write_bytes_per_sec: NonNegFloat
    read_ops_per_sec: NonNegFloat
    write_ops_per_sec: NonNegFloat
    busy_percent: Percent | None = None


class DiskMetrics(WireModel):
    filesystems: list[FilesystemUsage] = Field(default_factory=list, max_length=64)
    io: list[DiskIO] = Field(default_factory=list, max_length=128)


class NetworkInterface(WireModel):
    name: ShortStr
    is_up: bool
    speed_mbps: NonNegInt | None = None
    mtu: NonNegInt | None = None
    addresses: list[ShortStr] = Field(default_factory=list, max_length=16)
    rx_bytes: Counter
    tx_bytes: Counter
    rx_packets: Counter
    tx_packets: Counter
    rx_errors: Counter = 0
    tx_errors: Counter = 0
    rx_dropped: Counter = 0
    tx_dropped: Counter = 0
    rx_bytes_per_sec: NonNegFloat = 0
    tx_bytes_per_sec: NonNegFloat = 0
    rx_packets_per_sec: NonNegFloat = 0
    tx_packets_per_sec: NonNegFloat = 0
    errors_per_sec: NonNegFloat = 0
    drops_per_sec: NonNegFloat = 0


class NetworkMetrics(WireModel):
    interfaces: list[NetworkInterface] = Field(default_factory=list, max_length=128)
    # Socket counts per TCP state (ESTABLISHED, LISTEN, TIME_WAIT, ...).
    tcp_states: dict[ShortStr, NonNegInt] | None = Field(default=None, max_length=16)


class TemperatureSensor(WireModel):
    chip: ShortStr
    label: ShortStr
    kind: Literal["cpu", "gpu", "nvme", "disk", "wifi", "acpi", "other"] = "other"
    current_c: Celsius
    high_c: Celsius | None = None
    critical_c: Celsius | None = None


class SensorMetrics(WireModel):
    temperatures: list[TemperatureSensor] = Field(default_factory=list, max_length=128)


class ProcessInfo(WireModel):
    pid: int = Field(ge=0)
    name: str = Field(max_length=128)
    username: ShortStr | None = None
    cpu_percent: float = Field(ge=0, le=100 * 4096)
    memory_percent: Percent
    memory_rss_bytes: Counter
    status: ShortStr
    num_threads: NonNegInt | None = None
    cmdline: str | None = Field(default=None, max_length=512)


class ProcessMetrics(WireModel):
    total: NonNegInt
    running: NonNegInt | None = None
    top_cpu: list[ProcessInfo] = Field(default_factory=list, max_length=50)
    top_memory: list[ProcessInfo] = Field(default_factory=list, max_length=50)


class HostMetrics(WireModel):
    uptime_seconds: NonNegFloat
    boot_time: AwareDatetime


class AgentSelfMetrics(WireModel):
    version: ShortStr
    cpu_percent: float = Field(ge=0, le=100 * 4096)
    memory_rss_bytes: Counter
    collection_duration_ms: NonNegFloat
    queue_size: NonNegInt
    failed_requests_total: NonNegInt
    dropped_samples_total: NonNegInt = 0
    collector_errors: list[ShortStr] = Field(default_factory=list, max_length=32)


class MetricSampleIn(WireModel):
    schema_version: Literal[1] = 1
    agent_id: AgentId
    timestamp: AwareDatetime
    interval_seconds: float = Field(gt=0, le=3600)
    cpu: CpuMetrics
    memory: MemoryMetrics
    disks: DiskMetrics
    network: NetworkMetrics
    sensors: SensorMetrics = Field(default_factory=SensorMetrics)
    processes: ProcessMetrics
    host: HostMetrics
    agent: AgentSelfMetrics


class SystemInfo(WireModel):
    """Static machine facts; sent on agent start-up, not with every sample."""

    hostname: ShortStr
    os_name: MediumStr
    os_version: ShortStr | None = None
    kernel: ShortStr
    architecture: ShortStr
    cpu_model: MediumStr | None = None
    cpu_physical_cores: int | None = Field(default=None, ge=1)
    cpu_logical_cores: int = Field(ge=1)
    memory_total_bytes: Counter
    boot_time: AwareDatetime
    agent_version: ShortStr
    runtime: ShortStr | None = None


class MetricBatchIn(WireModel):
    agent_id: AgentId
    system_info: SystemInfo | None = None
    samples: list[MetricSampleIn] = Field(min_length=1, max_length=500)


class RejectedSample(ApiModel):
    index: int
    reason: str


class IngestResult(ApiModel):
    accepted: int
    duplicates: int
    rejected: list[RejectedSample]


# ---- Query side -----------------------------------------------------------


class HistoryResponse(ApiModel):
    agent_id: str
    start: datetime
    end: datetime
    source: Literal["raw", "1h", "1d"]
    bucket_seconds: int
    metrics: list[str]
    # Each point: {"t": iso timestamp, "<metric>": avg value or null, ...}
    points: list[dict[str, float | str | None]]


class MetricStats(ApiModel):
    metric: str
    samples: int
    avg: float | None
    min: float | None
    max: float | None
    p50: float | None
    p95: float | None
    p99: float | None


class StatsResponse(ApiModel):
    agent_id: str
    start: datetime
    end: datetime
    source: Literal["raw", "1h", "1d"]
    # Percentiles are exact only when computed from raw samples.
    percentiles_exact: bool
    stats: list[MetricStats]


class LatestSample(ApiModel):
    agent_id: str
    timestamp: datetime
    summary: dict[str, float | None]
    details: dict[str, object]
