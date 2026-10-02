"""Metric ingestion pipeline: validate -> store -> update agent -> alert -> broadcast."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Agent, MetricSample
from app.schemas.metrics import IngestResult, MetricBatchIn, MetricSampleIn, RejectedSample
from app.services.alerts.engine import AlertEngine
from app.services.events import agent_status_event, sample_event
from app.websocket.hub import Hub

log = logging.getLogger("ingestion")


def summarize(sample: MetricSampleIn) -> dict[str, float | None]:
    """Reduce a sample to the scalar metrics of ``app.metrics_catalog``."""
    interfaces = sample.network.interfaces
    filesystems = sample.disks.filesystems
    temps = sample.sensors.temperatures
    return {
        "cpu_percent": sample.cpu.usage_percent,
        "load_1m": sample.cpu.load_1m,
        "load_5m": sample.cpu.load_5m,
        "load_15m": sample.cpu.load_15m,
        "memory_percent": sample.memory.usage_percent,
        "memory_used_bytes": float(sample.memory.used_bytes),
        "swap_percent": sample.memory.swap_percent,
        "disk_percent_max": max((f.usage_percent for f in filesystems), default=None),
        "disk_read_bps": sum(d.read_bytes_per_sec for d in sample.disks.io),
        "disk_write_bps": sum(d.write_bytes_per_sec for d in sample.disks.io),
        "net_rx_bps": sum(i.rx_bytes_per_sec for i in interfaces),
        "net_tx_bps": sum(i.tx_bytes_per_sec for i in interfaces),
        "net_rx_pps": sum(i.rx_packets_per_sec for i in interfaces),
        "net_tx_pps": sum(i.tx_packets_per_sec for i in interfaces),
        "net_errors_ps": sum(i.errors_per_sec for i in interfaces),
        "net_drops_ps": sum(i.drops_per_sec for i in interfaces),
        "temperature_max_c": max((t.current_c for t in temps), default=None),
        "process_count": float(sample.processes.total),
        "uptime_seconds": sample.host.uptime_seconds,
    }


def _rejection_reason(sample: MetricSampleIn, now: datetime, settings: Settings) -> str | None:
    if sample.timestamp > now + timedelta(seconds=settings.max_clock_skew_seconds):
        return "timestamp is in the future (check the agent's clock)"
    if sample.timestamp < now - timedelta(hours=settings.raw_retention_hours):
        return "timestamp is older than the raw retention window"
    return None


@dataclass
class IngestionPipeline:
    settings: Settings
    hub: Hub
    alert_engine: AlertEngine

    async def ingest(
        self, db: AsyncSession, agent: Agent, batch: MetricBatchIn, ip: str
    ) -> IngestResult:
        now = datetime.now(UTC)
        rejected: list[RejectedSample] = []
        rows: list[dict[str, object]] = []
        newest: tuple[MetricSampleIn, dict[str, float | None]] | None = None

        for index, sample in enumerate(batch.samples):
            reason = _rejection_reason(sample, now, self.settings)
            if reason:
                rejected.append(RejectedSample(index=index, reason=reason))
                continue
            summary = summarize(sample)
            rows.append(self._row(agent, sample, summary))
            if newest is None or sample.timestamp > newest[0].timestamp:
                newest = (sample, summary)

        inserted = 0
        if rows:
            # Duplicate (agent, ts) pairs are re-uploads after a lost response;
            # ignoring them makes ingestion idempotent for at-least-once agents.
            stmt = (
                insert(MetricSample)
                .values(rows)
                .on_conflict_do_nothing()
                .returning(MetricSample.ts)
            )
            inserted = len((await db.execute(stmt)).all())

        came_online = self._touch_agent(agent, batch, newest[0] if newest else None, now, ip)
        await db.commit()

        if came_online:
            events = await self.alert_engine.agent_came_online(db, agent, now)
            await db.commit()
            await self.alert_engine.dispatch(events)
            self.hub.publish(agent_status_event(agent.agent_id, "online"))
        if newest is not None:
            await self._after_store(db, agent, *newest, now=now)

        log.info(
            "metrics.ingested",
            extra={
                "agent_id": agent.agent_id,
                "accepted": inserted,
                "duplicates": len(rows) - inserted,
                "rejected": len(rejected),
            },
        )
        return IngestResult(accepted=inserted, duplicates=len(rows) - inserted, rejected=rejected)

    async def _after_store(
        self,
        db: AsyncSession,
        agent: Agent,
        sample: MetricSampleIn,
        summary: dict[str, float | None],
        *,
        now: datetime,
    ) -> None:
        # Old buffered samples are history: they are stored but neither
        # broadcast as "live" nor allowed to (re)fire alerts.
        fresh_after = now - timedelta(seconds=self.settings.agent_offline_after_seconds)
        if sample.timestamp < fresh_after:
            return
        self.hub.publish(sample_event(agent.agent_id, sample.timestamp, summary))
        await self.alert_engine.evaluate_sample(db, agent, summary, sample.timestamp)

    @staticmethod
    def _row(
        agent: Agent, sample: MetricSampleIn, summary: dict[str, float | None]
    ) -> dict[str, object]:
        return {
            "agent_pk": agent.id,
            "ts": sample.timestamp,
            **summary,
            "process_count": sample.processes.total,
            "details": sample.model_dump(
                mode="json",
                include={"cpu", "memory", "disks", "network", "sensors", "processes", "agent"},
            ),
        }

    @staticmethod
    def _touch_agent(
        agent: Agent,
        batch: MetricBatchIn,
        newest: MetricSampleIn | None,
        now: datetime,
        ip: str,
    ) -> bool:
        """Update heartbeat fields; return True if the agent just came online."""
        # The heartbeat uses the *server* clock, so a skewed agent clock cannot
        # make a machine look online or offline.
        agent.last_seen_at = now
        agent.last_ip = ip
        if batch.system_info is not None:
            agent.system_info = batch.system_info.model_dump(mode="json")
            agent.agent_version = batch.system_info.agent_version
        elif newest is not None:
            agent.agent_version = newest.agent.version
        was_online = agent.is_online
        agent.is_online = True
        return not was_online
