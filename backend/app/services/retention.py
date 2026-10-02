"""Downsampling and retention (see docs/retention.md).

    raw samples (5 s) --hourly rollup--> 1h rollups --daily rollup--> 1d rollups
       kept RAW_RETENTION_HOURS          METRIC_RETENTION_DAYS        DAILY_RETENTION_DAYS

Rollups are recomputed over a trailing window on every run and upserted, which
makes the job idempotent and lets late-arriving buffered samples (from agents
that were offline) be folded into their correct buckets.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.metrics_catalog import METRIC_NAMES
from app.models import Alert, MetricRollup, MetricSample
from app.services.auth_service import purge_expired_sessions

log = logging.getLogger("retention")

HOURLY_LOOKBACK = timedelta(hours=6)
DAILY_LOOKBACK = timedelta(days=2)


async def rollup_hourly(db: AsyncSession, since: datetime) -> int:
    hour = func.date_trunc("hour", MetricSample.ts, "UTC").label("bucket")
    columns = []
    for m in METRIC_NAMES:
        col = getattr(MetricSample, m)
        columns += [
            func.count(col).label(f"{m}__n"),
            func.avg(col).label(f"{m}__avg"),
            func.min(col).label(f"{m}__min"),
            func.max(col).label(f"{m}__max"),
        ]
    query = (
        select(MetricSample.agent_pk, hour, *columns)
        .where(MetricSample.ts >= since)
        .group_by(MetricSample.agent_pk, hour)
    )
    rows = []
    for r in (await db.execute(query)).mappings():
        for m in METRIC_NAMES:
            if r[f"{m}__n"]:  # all-NULL metric (e.g. no sensors) -> no rollup row
                rows.append(
                    {
                        "agent_pk": r["agent_pk"],
                        "resolution": "1h",
                        "metric": m,
                        "bucket_start": r["bucket"],
                        "avg": r[f"{m}__avg"],
                        "min": r[f"{m}__min"],
                        "max": r[f"{m}__max"],
                        "sample_count": r[f"{m}__n"],
                    }
                )
    if not rows:
        return 0
    # asyncpg caps a statement at 32767 bind parameters; 8 per row.
    for chunk_start in range(0, len(rows), 2000):
        stmt = insert(MetricRollup).values(rows[chunk_start : chunk_start + 2000])
        stmt = stmt.on_conflict_do_update(
            index_elements=["agent_pk", "resolution", "metric", "bucket_start"],
            set_={c: stmt.excluded[c] for c in ("avg", "min", "max", "sample_count")},
        )
        await db.execute(stmt)
    return len(rows)


_DAILY_SQL = text(
    """
    INSERT INTO metric_rollups (agent_pk, resolution, metric, bucket_start, avg, min, max,
                                sample_count)
    SELECT agent_pk, '1d', metric, date_trunc('day', bucket_start, 'UTC'),
           sum(avg * sample_count) / sum(sample_count), min(min), max(max), sum(sample_count)
    FROM metric_rollups
    WHERE resolution = '1h' AND bucket_start >= :since
    GROUP BY agent_pk, metric, date_trunc('day', bucket_start, 'UTC')
    ON CONFLICT (agent_pk, resolution, metric, bucket_start) DO UPDATE
    SET avg = EXCLUDED.avg, min = EXCLUDED.min, max = EXCLUDED.max,
        sample_count = EXCLUDED.sample_count
    """
)


async def rollup_daily(db: AsyncSession, since: datetime) -> None:
    await db.execute(_DAILY_SQL, {"since": since})


async def purge(db: AsyncSession, settings: Settings, now: datetime) -> dict[str, int]:
    def _count(result: object) -> int:
        return int(getattr(result, "rowcount", 0) or 0)

    raw_cutoff = now - timedelta(hours=settings.raw_retention_hours)
    hourly_cutoff = now - timedelta(days=settings.metric_retention_days)
    daily_cutoff = now - timedelta(days=settings.daily_retention_days)
    return {
        "raw": _count(await db.execute(delete(MetricSample).where(MetricSample.ts < raw_cutoff))),
        "hourly": _count(
            await db.execute(
                delete(MetricRollup).where(
                    MetricRollup.resolution == "1h", MetricRollup.bucket_start < hourly_cutoff
                )
            )
        ),
        "daily": _count(
            await db.execute(
                delete(MetricRollup).where(
                    MetricRollup.resolution == "1d", MetricRollup.bucket_start < daily_cutoff
                )
            )
        ),
        "alerts": _count(
            await db.execute(
                delete(Alert).where(Alert.status == "resolved", Alert.resolved_at < daily_cutoff)
            )
        ),
        "sessions": await purge_expired_sessions(db),
    }


async def run_retention(db: AsyncSession, settings: Settings, now: datetime) -> None:
    hourly_rows = await rollup_hourly(db, now - HOURLY_LOOKBACK)
    await rollup_daily(db, now - DAILY_LOOKBACK)
    # Rollups are committed before raw data is deleted so a crash between the
    # two steps can never lose data that was not yet aggregated.
    await db.commit()
    deleted = await purge(db, settings, now)
    await db.commit()
    log.info("retention.completed", extra={"hourly_rows": hourly_rows, "deleted": deleted})
