from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models import MetricRollup, MetricSample
from app.services.history import plan_query
from app.services.retention import run_retention
from tests.conftest import agent_headers, make_settings
from tests.factories import make_sample


async def _ingest_series(client: httpx.AsyncClient, creds, start: datetime, values: list[float]):
    samples = [
        make_sample("web-1", start + timedelta(seconds=5 * i), cpu=v) for i, v in enumerate(values)
    ]
    for i in range(0, len(samples), 100):
        resp = await client.post(
            "/api/v1/metrics/batch",
            json={"agent_id": "web-1", "samples": samples[i : i + 100]},
            headers=agent_headers(creds),
        )
        assert resp.status_code == 200, resp.text


@pytest.mark.parametrize(
    ("span", "source", "bucket"),
    [
        (timedelta(minutes=5), "raw", 5),
        (timedelta(hours=1), "raw", 15),
        (timedelta(hours=24), "raw", 300),
        (timedelta(days=7), "1h", 3600),
        (timedelta(days=30), "1h", 10800),
        (timedelta(days=90), "1d", 86400),
    ],
)
def test_query_planner(span: timedelta, source: str, bucket: int):
    now = datetime.now(UTC)
    plan = plan_query(now - span, now, now, make_settings())
    assert (plan.source, plan.bucket_seconds) == (source, bucket)


async def test_history_and_exact_stats(admin_client: httpx.AsyncClient, agent_creds):
    start = datetime.now(UTC) - timedelta(minutes=9)
    values = [float(i) for i in range(1, 101)]  # 1..100 over ~8 minutes
    await _ingest_series(admin_client, agent_creds, start, values)

    hist = (
        await admin_client.get("/api/v1/metrics/web-1?range=15m&metrics=cpu_percent,net_rx_bps")
    ).json()
    assert hist["source"] == "raw"
    assert hist["metrics"] == ["cpu_percent", "net_rx_bps"]
    assert len(hist["points"]) > 20
    assert all("cpu_percent" in p and "t" in p for p in hist["points"])

    stats = (
        await admin_client.get("/api/v1/metrics/web-1/stats?range=15m&metrics=cpu_percent")
    ).json()
    cpu = stats["stats"][0]
    assert stats["percentiles_exact"] is True
    assert cpu["samples"] == 100
    assert cpu["min"] == 1 and cpu["max"] == 100
    assert cpu["avg"] == pytest.approx(50.5)
    assert cpu["p95"] == pytest.approx(95.05)


async def test_explicit_window_query(admin_client: httpx.AsyncClient, agent_creds):
    start = datetime.now(UTC) - timedelta(minutes=10)
    await _ingest_series(admin_client, agent_creds, start, [10.0] * 60 + [90.0] * 60)
    # Only the second half of the series (all 90%).
    window_start = start + timedelta(seconds=5 * 60)
    resp = await admin_client.get(
        "/api/v1/metrics/web-1/stats",
        params={"start": window_start.isoformat(), "metrics": "cpu_percent"},
    )
    cpu = resp.json()["stats"][0]
    assert cpu["min"] == 90 and cpu["samples"] == 60


async def test_gaps_become_null_points(admin_client: httpx.AsyncClient, agent_creds):
    now = datetime.now(UTC)
    headers = agent_headers(agent_creds)
    for ts in (now - timedelta(minutes=10), now - timedelta(minutes=1)):
        await admin_client.post("/api/v1/metrics", json=make_sample("web-1", ts), headers=headers)
    points = (await admin_client.get("/api/v1/metrics/web-1?range=15m")).json()["points"]
    assert len(points) == 3
    assert points[1]["cpu_percent"] is None


async def test_invalid_queries(admin_client: httpx.AsyncClient, agent_creds):
    assert (await admin_client.get("/api/v1/metrics/web-1?range=2y")).status_code == 422
    resp = await admin_client.get("/api/v1/metrics/web-1?range=1h&metrics=cpu_percent;drop")
    assert resp.status_code == 422
    assert (await admin_client.get("/api/v1/metrics/web-1")).status_code == 422
    assert (await admin_client.get("/api/v1/metrics/nope?range=1h")).status_code == 404


async def test_rollups_and_retention(
    admin_client: httpx.AsyncClient, agent_creds, engine: AsyncEngine
):
    now = datetime.now(UTC)
    start = now - timedelta(minutes=30)
    await _ingest_series(admin_client, agent_creds, start, [20.0] * 50 + [80.0] * 50)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        await run_retention(db, make_settings(), now)
        rollups = (
            (
                await db.execute(
                    select(MetricRollup).where(
                        MetricRollup.metric == "cpu_percent", MetricRollup.resolution == "1h"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert sum(r.sample_count for r in rollups) == 100
    assert min(r.min for r in rollups) == 20 and max(r.max for r in rollups) == 80

    # Re-running is idempotent.
    async with sessionmaker() as db:
        await run_retention(db, make_settings(), now)
        total = (
            await db.execute(
                select(func.sum(MetricRollup.sample_count)).where(
                    MetricRollup.metric == "cpu_percent", MetricRollup.resolution == "1h"
                )
            )
        ).scalar()
    assert total == 100

    # A 7-day query is served from hourly rollups; percentiles are not invented.
    stats = (
        await admin_client.get("/api/v1/metrics/web-1/stats?range=7d&metrics=cpu_percent")
    ).json()
    assert stats["source"] == "1h" and stats["percentiles_exact"] is False
    assert stats["stats"][0]["avg"] == pytest.approx(50.0)
    assert stats["stats"][0]["p95"] is None

    # Raw samples past retention are purged; rollups survive.
    async with sessionmaker() as db:
        await run_retention(db, make_settings(raw_retention_hours=0), now)
        raw = (await db.execute(select(func.count()).select_from(MetricSample))).scalar()
        kept = (await db.execute(select(func.count()).select_from(MetricRollup))).scalar()
    assert raw == 0 and kept > 0
