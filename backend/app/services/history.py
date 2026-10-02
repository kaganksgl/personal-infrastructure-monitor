"""Historical metric queries.

The query planner picks the cheapest table that still covers the requested
range and a bucket size that yields at most ~``TARGET_POINTS`` points:

=========  ===========  ============
range      source       bucket
=========  ===========  ============
5m - 24h   raw samples  5 s - 5 min
7d         1h rollups   1 h
30d        1h rollups   3 h
older      1d rollups   >= 1 d
=========  ===========  ============
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.functions import Function

from app.config import Settings
from app.models import MetricRollup, MetricSample
from app.schemas.metrics import MetricStats

Source = Literal["raw", "1h", "1d"]

RANGES: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
TARGET_POINTS = 300
_NICE_BUCKETS = (5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200)
_DAY = 86400
_ORIGIN = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class QueryPlan:
    source: Source
    bucket_seconds: int


def plan_query(start: datetime, end: datetime, now: datetime, settings: Settings) -> QueryPlan:
    span = (end - start).total_seconds()
    wanted = span / TARGET_POINTS
    bucket = next((b for b in _NICE_BUCKETS if b >= wanted), _DAY * max(1, round(wanted / _DAY)))
    if start >= now - timedelta(hours=settings.raw_retention_hours):
        return QueryPlan("raw", bucket)
    if start >= now - timedelta(days=settings.metric_retention_days):
        return QueryPlan("1h", max(bucket, 3600))
    return QueryPlan("1d", max(bucket, _DAY))


def _bin(bucket_seconds: int, column: InstrumentedAttribute[datetime]) -> Function[datetime]:
    return func.date_bin(timedelta(seconds=bucket_seconds), column, _ORIGIN)


async def fetch_series(
    db: AsyncSession,
    agent_pk: int,
    metrics: list[str],
    start: datetime,
    end: datetime,
    plan: QueryPlan,
) -> list[dict[str, float | str | None]]:
    if plan.source == "raw":
        buckets = await _raw_series(db, agent_pk, metrics, start, end, plan.bucket_seconds)
    else:
        buckets = await _rollup_series(db, agent_pk, metrics, start, end, plan)
    return _with_gaps(buckets, metrics, plan.bucket_seconds)


async def _raw_series(
    db: AsyncSession,
    agent_pk: int,
    metrics: list[str],
    start: datetime,
    end: datetime,
    bucket_seconds: int,
) -> dict[datetime, dict[str, float | None]]:
    t = _bin(bucket_seconds, MetricSample.ts).label("bucket")
    # Metric names were validated against the catalog, so getattr is safe;
    # SQLAlchemy emits column identifiers, never interpolated strings.
    columns = [func.avg(getattr(MetricSample, m)).label(m) for m in metrics]
    query = (
        select(t, *columns)
        .where(MetricSample.agent_pk == agent_pk, MetricSample.ts >= start, MetricSample.ts < end)
        .group_by(t)
        .order_by(t)
    )
    buckets: dict[datetime, dict[str, float | None]] = {}
    for row in await db.execute(query):
        ts: datetime = row.bucket
        buckets[ts] = {m: getattr(row, m) for m in metrics}
    return buckets


async def _rollup_series(
    db: AsyncSession,
    agent_pk: int,
    metrics: list[str],
    start: datetime,
    end: datetime,
    plan: QueryPlan,
) -> dict[datetime, dict[str, float | None]]:
    t = _bin(plan.bucket_seconds, MetricRollup.bucket_start).label("bucket")
    weighted_avg = func.sum(MetricRollup.avg * MetricRollup.sample_count) / func.sum(
        MetricRollup.sample_count
    )
    query = (
        select(t, MetricRollup.metric, weighted_avg.label("value"))
        .where(
            MetricRollup.agent_pk == agent_pk,
            MetricRollup.resolution == plan.source,
            MetricRollup.metric.in_(metrics),
            MetricRollup.bucket_start >= start,
            MetricRollup.bucket_start < end,
        )
        .group_by(t, MetricRollup.metric)
        .order_by(t)
    )
    buckets: dict[datetime, dict[str, float | None]] = {}
    for row in await db.execute(query):
        ts: datetime = row.bucket
        buckets.setdefault(ts, dict.fromkeys(metrics))[row.metric] = row.value
    return buckets


def _with_gaps(
    buckets: dict[datetime, dict[str, float | None]], metrics: list[str], bucket_seconds: int
) -> list[dict[str, float | str | None]]:
    """Insert a null point wherever data is missing so charts break the line
    instead of drawing a misleading straight segment across an outage."""
    points: list[dict[str, float | str | None]] = []
    previous: datetime | None = None
    for ts in sorted(buckets):
        if previous is not None and (ts - previous).total_seconds() > 2 * bucket_seconds:
            gap = previous + timedelta(seconds=bucket_seconds)
            points.append({"t": gap.isoformat(), **dict.fromkeys(metrics)})
        points.append({"t": ts.isoformat(), **buckets[ts]})
        previous = ts
    return points


async def fetch_stats(
    db: AsyncSession,
    agent_pk: int,
    metrics: list[str],
    start: datetime,
    end: datetime,
    source: Source,
) -> list[MetricStats]:
    if source == "raw":
        return await _raw_stats(db, agent_pk, metrics, start, end)
    return await _rollup_stats(db, agent_pk, metrics, start, end, source)


async def _raw_stats(
    db: AsyncSession, agent_pk: int, metrics: list[str], start: datetime, end: datetime
) -> list[MetricStats]:
    columns = []
    for m in metrics:
        col = getattr(MetricSample, m)
        columns += [
            func.count(col).label(f"{m}__n"),
            func.avg(col).label(f"{m}__avg"),
            func.min(col).label(f"{m}__min"),
            func.max(col).label(f"{m}__max"),
            *(
                cast(func.percentile_cont(q).within_group(col), Float).label(
                    f"{m}__p{int(q * 100)}"
                )
                for q in (0.5, 0.95, 0.99)
            ),
        ]
    row = (
        (
            await db.execute(
                select(*columns).where(
                    MetricSample.agent_pk == agent_pk,
                    MetricSample.ts >= start,
                    MetricSample.ts < end,
                )
            )
        )
        .one()
        ._mapping
    )
    return [
        MetricStats(
            metric=m,
            samples=row[f"{m}__n"],
            avg=row[f"{m}__avg"],
            min=row[f"{m}__min"],
            max=row[f"{m}__max"],
            p50=row[f"{m}__p50"],
            p95=row[f"{m}__p95"],
            p99=row[f"{m}__p99"],
        )
        for m in metrics
    ]


async def _rollup_stats(
    db: AsyncSession,
    agent_pk: int,
    metrics: list[str],
    start: datetime,
    end: datetime,
    source: Source,
) -> list[MetricStats]:
    """Avg/min/max are exact from rollups; percentiles are not recoverable from
    pre-aggregated data, so they are reported as null rather than guessed."""
    n = func.sum(MetricRollup.sample_count)
    query = (
        select(
            MetricRollup.metric,
            n.label("n"),
            (func.sum(MetricRollup.avg * MetricRollup.sample_count) / n).label("avg"),
            func.min(MetricRollup.min).label("min"),
            func.max(MetricRollup.max).label("max"),
        )
        .where(
            MetricRollup.agent_pk == agent_pk,
            MetricRollup.resolution == source,
            MetricRollup.metric.in_(metrics),
            MetricRollup.bucket_start >= start,
            MetricRollup.bucket_start < end,
        )
        .group_by(MetricRollup.metric)
    )
    found = {row.metric: row for row in await db.execute(query)}
    stats = []
    for m in metrics:
        row = found.get(m)
        stats.append(
            MetricStats(
                metric=m,
                samples=int(row.n) if row else 0,
                avg=row.avg if row else None,
                min=row.min if row else None,
                max=row.max if row else None,
                p50=None,
                p95=None,
                p99=None,
            )
        )
    return stats


async def latest_sample(db: AsyncSession, agent_pk: int) -> MetricSample | None:
    query = (
        select(MetricSample)
        .where(MetricSample.agent_pk == agent_pk)
        .order_by(MetricSample.ts.desc())
        .limit(1)
    )
    return (await db.execute(query)).scalar_one_or_none()
