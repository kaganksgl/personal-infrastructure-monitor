from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Double, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MetricSample(Base):
    """One raw sample from one agent.

    Hybrid layout: scalar metrics that are charted, aggregated and alerted on
    get their own typed columns (fast range scans, no JSON parsing); the
    variable-cardinality detail (per-core, per-interface, per-disk, sensors,
    process lists) lives in ``details``. The composite primary key doubles as
    the time-range index and makes re-uploads idempotent.
    """

    __tablename__ = "metric_samples"

    agent_pk: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    cpu_percent: Mapped[float] = mapped_column(Double)
    load_1m: Mapped[float] = mapped_column(Double)
    load_5m: Mapped[float] = mapped_column(Double)
    load_15m: Mapped[float] = mapped_column(Double)
    memory_percent: Mapped[float] = mapped_column(Double)
    memory_used_bytes: Mapped[float] = mapped_column(Double)
    swap_percent: Mapped[float] = mapped_column(Double)
    disk_percent_max: Mapped[float | None] = mapped_column(Double)
    disk_read_bps: Mapped[float] = mapped_column(Double)
    disk_write_bps: Mapped[float] = mapped_column(Double)
    net_rx_bps: Mapped[float] = mapped_column(Double)
    net_tx_bps: Mapped[float] = mapped_column(Double)
    net_rx_pps: Mapped[float] = mapped_column(Double)
    net_tx_pps: Mapped[float] = mapped_column(Double)
    net_errors_ps: Mapped[float] = mapped_column(Double)
    net_drops_ps: Mapped[float] = mapped_column(Double)
    temperature_max_c: Mapped[float | None] = mapped_column(Double)

    process_count: Mapped[int] = mapped_column(Integer)
    uptime_seconds: Mapped[float] = mapped_column(Double)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)


class MetricRollup(Base):
    """Pre-aggregated metric (long format: one row per metric per bucket).

    Long format means new metrics need no schema change, and the row count stays
    small: 17 metrics x 24 h x 30 d is ~12k rows per agent for the hourly tier.
    """

    __tablename__ = "metric_rollups"
    __table_args__ = (CheckConstraint("resolution IN ('1h', '1d')", name="resolution"),)

    agent_pk: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    resolution: Mapped[str] = mapped_column(String(2), primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    avg: Mapped[float] = mapped_column(Double)
    min: Mapped[float] = mapped_column(Double)
    max: Mapped[float] = mapped_column(Double)
    sample_count: Mapped[int] = mapped_column(Integer)
