from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.auth.dependencies import (
    AppSettings,
    AuthenticatedAgent,
    CurrentUser,
    DbSession,
    client_ip,
)
from app.metrics_catalog import METRIC_NAMES, METRICS
from app.models import Agent
from app.schemas.metrics import (
    HistoryResponse,
    IngestResult,
    LatestSample,
    MetricBatchIn,
    MetricSampleIn,
    StatsResponse,
)
from app.services import agents as agent_service
from app.services import history

router = APIRouter(prefix="/metrics", tags=["metrics"])

_MAX_SPAN = timedelta(days=400)
_DEFAULT_METRICS = ("cpu_percent", "memory_percent")


async def _ingest(
    request: Request, db: DbSession, agent: Agent, batch: MetricBatchIn, settings: AppSettings
) -> IngestResult:
    if batch.agent_id != agent.agent_id or any(s.agent_id != agent.agent_id for s in batch.samples):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "agent_id does not match credentials")
    if len(batch.samples) > settings.max_batch_size:
        raise HTTPException(
            413,
            f"Batch exceeds {settings.max_batch_size} samples",
        )
    pipeline = request.app.state.pipeline
    result: IngestResult = await pipeline.ingest(db, agent, batch, client_ip(request))
    return result


@router.post("", response_model=IngestResult, tags=["agent protocol"])
async def ingest_sample(
    sample: MetricSampleIn,
    request: Request,
    db: DbSession,
    agent: AuthenticatedAgent,
    settings: AppSettings,
) -> IngestResult:
    """Ingest a single sample."""
    batch = MetricBatchIn(agent_id=sample.agent_id, samples=[sample])
    return await _ingest(request, db, agent, batch, settings)


@router.post("/batch", response_model=IngestResult, tags=["agent protocol"])
async def ingest_batch(
    batch: MetricBatchIn,
    request: Request,
    db: DbSession,
    agent: AuthenticatedAgent,
    settings: AppSettings,
) -> IngestResult:
    """Ingest several samples (used by agents to flush their offline buffer)."""
    return await _ingest(request, db, agent, batch, settings)


@router.get("/catalog")
async def metric_catalog(_: CurrentUser) -> list[dict[str, str]]:
    return [{"name": m.name, "label": m.label, "unit": m.unit.value} for m in METRICS.values()]


def _resolve_window(
    range_: str | None, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if range_ is not None:
        if range_ not in history.RANGES:
            raise HTTPException(
                422,
                f"range must be one of {', '.join(history.RANGES)}",
            )
        return now - history.RANGES[range_], now
    if start is None:
        raise HTTPException(422, "Provide range or start")
    end = end or now
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Timestamps need a timezone")
    if not timedelta(0) < end - start <= _MAX_SPAN:
        raise HTTPException(422, "Invalid time window")
    return start, end


def _parse_metrics(raw: str | None) -> list[str]:
    if not raw:
        return list(_DEFAULT_METRICS)
    names = list(dict.fromkeys(m.strip() for m in raw.split(",") if m.strip()))
    unknown = [m for m in names if m not in METRIC_NAMES]
    if unknown or not names:
        raise HTTPException(422, f"Unknown metrics: {', '.join(unknown)}")
    return names


async def _agent_or_404(db: DbSession, agent_id: str) -> Agent:
    agent = await agent_service.get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


RangeQuery = Annotated[
    str | None, Query(alias="range", description="5m, 15m, 1h, 6h, 24h, 7d, 30d")
]
MetricsQuery = Annotated[str | None, Query(description="Comma-separated metric names")]


@router.get("/{agent_id}", response_model=HistoryResponse)
async def metric_history(
    agent_id: str,
    db: DbSession,
    settings: AppSettings,
    _: CurrentUser,
    range_: RangeQuery = None,
    start: datetime | None = None,
    end: datetime | None = None,
    metrics: MetricsQuery = None,
) -> HistoryResponse:
    """Time series for one agent, either by preset ``range`` or explicit ``start``/``end``."""
    agent = await _agent_or_404(db, agent_id)
    names = _parse_metrics(metrics)
    window_start, window_end = _resolve_window(range_, start, end)
    plan = history.plan_query(window_start, window_end, datetime.now(UTC), settings)
    points = await history.fetch_series(db, agent.id, names, window_start, window_end, plan)
    return HistoryResponse(
        agent_id=agent_id,
        start=window_start,
        end=window_end,
        source=plan.source,
        bucket_seconds=plan.bucket_seconds,
        metrics=names,
        points=points,
    )


@router.get("/{agent_id}/stats", response_model=StatsResponse)
async def metric_stats(
    agent_id: str,
    db: DbSession,
    settings: AppSettings,
    _: CurrentUser,
    range_: RangeQuery = None,
    start: datetime | None = None,
    end: datetime | None = None,
    metrics: MetricsQuery = None,
) -> StatsResponse:
    """Average, minimum, maximum and P50/P95/P99 over a window."""
    agent = await _agent_or_404(db, agent_id)
    names = _parse_metrics(metrics)
    window_start, window_end = _resolve_window(range_, start, end)
    plan = history.plan_query(window_start, window_end, datetime.now(UTC), settings)
    stats = await history.fetch_stats(db, agent.id, names, window_start, window_end, plan.source)
    return StatsResponse(
        agent_id=agent_id,
        start=window_start,
        end=window_end,
        source=plan.source,
        percentiles_exact=plan.source == "raw",
        stats=stats,
    )


@router.get("/{agent_id}/latest", response_model=LatestSample)
async def latest_metrics(agent_id: str, db: DbSession, _: CurrentUser) -> LatestSample:
    """Newest full sample, including per-core, per-interface, sensor and process detail."""
    agent = await _agent_or_404(db, agent_id)
    sample = await history.latest_sample(db, agent.id)
    if sample is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No samples yet")
    summary = {m: getattr(sample, m) for m in METRIC_NAMES}
    summary["process_count"] = float(sample.process_count)
    summary["uptime_seconds"] = sample.uptime_seconds
    return LatestSample(
        agent_id=agent_id, timestamp=sample.ts, summary=summary, details=sample.details
    )
