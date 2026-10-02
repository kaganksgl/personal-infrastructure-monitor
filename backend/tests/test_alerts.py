from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Agent
from app.services.heartbeat import check_heartbeats
from tests.conftest import agent_headers
from tests.factories import make_sample


async def _post(client: httpx.AsyncClient, creds, **kwargs):  # type: ignore[no-untyped-def]
    resp = await client.post(
        "/api/v1/metrics", json=make_sample("web-1", **kwargs), headers=agent_headers(creds)
    )
    assert resp.status_code == 200, resp.text


async def _firing(client: httpx.AsyncClient) -> list[dict]:
    return (await client.get("/api/v1/alerts?status=firing")).json()


async def test_cpu_alert_requires_sustained_breach(admin_client: httpx.AsyncClient, agent_creds):
    t0 = datetime.now(UTC) - timedelta(seconds=20)
    await _post(admin_client, agent_creds, ts=t0 - timedelta(seconds=60), cpu=95)
    # Sample from 80 s ago is "history", must not start an alert timer:
    assert await _firing(admin_client) == []

    await _post(admin_client, agent_creds, ts=t0, cpu=95)
    await _post(admin_client, agent_creds, ts=t0 + timedelta(seconds=10), cpu=96)
    assert not [a for a in await _firing(admin_client) if a["metric"] == "cpu_percent"]

    # 60 s after the first fresh breach. (Timestamps may be up to 5 min in the future.)
    await _post(admin_client, agent_creds, ts=t0 + timedelta(seconds=60), cpu=94.7)
    (alert,) = [a for a in await _firing(admin_client) if a["metric"] == "cpu_percent"]
    assert alert["severity"] == "critical"
    assert alert["value"] == 94.7
    assert "94.7%" in alert["message"] and "for 60s" in alert["message"]

    # Still breaching: no duplicate alert.
    await _post(admin_client, agent_creds, ts=t0 + timedelta(seconds=65), cpu=99)
    assert len([a for a in await _firing(admin_client) if a["metric"] == "cpu_percent"]) == 1

    await _post(admin_client, agent_creds, ts=t0 + timedelta(seconds=70), cpu=10)
    assert not [a for a in await _firing(admin_client) if a["metric"] == "cpu_percent"]
    resolved = (await admin_client.get("/api/v1/alerts?status=resolved")).json()
    assert resolved[0]["resolved_at"] is not None


async def test_zero_duration_rule_fires_immediately_and_sets_warning(
    admin_client: httpx.AsyncClient, agent_creds
):
    await _post(admin_client, agent_creds, disk=91)
    (alert,) = await _firing(admin_client)
    assert alert["metric"] == "disk_percent_max" and alert["severity"] == "warning"
    agent = (await admin_client.get("/api/v1/agents/web-1")).json()
    assert agent["status"] == "warning" and agent["active_alerts"] == 1


async def test_missing_sensor_never_alerts(admin_client: httpx.AsyncClient, agent_creds):
    await _post(admin_client, agent_creds, temp=None)
    assert await _firing(admin_client) == []


async def test_acknowledge_alert(admin_client: httpx.AsyncClient, agent_creds):
    await _post(admin_client, agent_creds, disk=99)
    (alert,) = await _firing(admin_client)
    resp = await admin_client.post(f"/api/v1/alerts/{alert['id']}/acknowledge")
    assert resp.status_code == 200
    assert resp.json()["acknowledged_by"] == "admin"
    unacked = (await admin_client.get("/api/v1/alerts?unacknowledged=true")).json()
    assert unacked == []
    assert (await admin_client.post("/api/v1/alerts/999/acknowledge")).status_code == 404


async def test_offline_detection_and_recovery(
    admin_client: httpx.AsyncClient, agent_creds, app, engine: AsyncEngine
):
    await _post(admin_client, agent_creds)
    async with engine.begin() as conn:
        await conn.execute(
            update(Agent).values(last_seen_at=datetime.now(UTC) - timedelta(minutes=5))
        )
    async with app.state.db.sessionmaker() as db:
        went = await check_heartbeats(
            db, app.state.settings, app.state.alert_engine, app.state.hub, datetime.now(UTC)
        )
    assert went == ["web-1"]
    assert (await admin_client.get("/api/v1/agents/web-1")).json()["status"] == "offline"
    (alert,) = await _firing(admin_client)
    assert alert["metric"] == "agent_offline" and alert["severity"] == "critical"

    await _post(admin_client, agent_creds)
    assert await _firing(admin_client) == []
    assert (await admin_client.get("/api/v1/agents/web-1")).json()["status"] == "online"


async def test_rule_management(admin_client: httpx.AsyncClient, agent_creds):
    rules = (await admin_client.get("/api/v1/alerts/rules")).json()
    assert {r["metric"] for r in rules} >= {"cpu_percent", "agent_offline"}

    rule = {
        "name": "Busy web",
        "metric": "load_1m",
        "threshold": 0.1,
        "severity": "info",
        "agent_id": "web-1",
    }
    created = await admin_client.post("/api/v1/alerts/rules", json=rule)
    assert created.status_code == 201
    rule_id = created.json()["id"]
    await _post(admin_client, agent_creds)
    assert [a["rule_name"] for a in await _firing(admin_client)] == ["Busy web"]

    patched = await admin_client.patch(f"/api/v1/alerts/rules/{rule_id}", json={"enabled": False})
    assert patched.json()["enabled"] is False
    assert (await admin_client.delete(f"/api/v1/alerts/rules/{rule_id}")).status_code == 204

    bad = await admin_client.post("/api/v1/alerts/rules", json={**rule, "metric": "nope"})
    assert bad.status_code == 422
