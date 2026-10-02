import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import Agent, MetricSample
from tests.conftest import agent_headers
from tests.factories import make_sample


async def test_register_agent_returns_key_once_and_stores_hash(
    admin_client: httpx.AsyncClient, engine: AsyncEngine
):
    resp = await admin_client.post(
        "/api/v1/agents", json={"agent_id": "db-1", "display_name": "Database"}
    )
    assert resp.status_code == 201
    body = resp.json()
    key = body["api_key"]
    assert key.startswith("iwk_") and len(key) > 40
    assert body["agent"]["status"] == "pending"
    assert key.startswith(body["agent"]["api_key_prefix"])

    async with engine.connect() as conn:
        stored = (await conn.execute(select(Agent.api_key_hash))).scalar_one()
    assert stored != key and len(stored) == 64

    listing = (await admin_client.get("/api/v1/agents")).json()
    assert "api_key" not in listing[0] and "api_key_hash" not in listing[0]


async def test_duplicate_and_invalid_agent_ids(admin_client: httpx.AsyncClient):
    assert (await admin_client.post("/api/v1/agents", json={"agent_id": "a1"})).status_code == 201
    assert (await admin_client.post("/api/v1/agents", json={"agent_id": "a1"})).status_code == 409
    for bad in ("A", "UPPER", "has space", "../etc", "-leading"):
        resp = await admin_client.post("/api/v1/agents", json={"agent_id": bad})
        assert resp.status_code == 422, bad


async def test_rotate_key_invalidates_old_key(admin_client: httpx.AsyncClient, agent_creds):
    old = agent_headers(agent_creds)
    assert (await admin_client.get("/api/v1/agent/ping", headers=old)).status_code == 200

    new_key = (await admin_client.post("/api/v1/agents/web-1/rotate-key")).json()["api_key"]
    assert (await admin_client.get("/api/v1/agent/ping", headers=old)).status_code == 401
    new = agent_headers({"agent_id": "web-1", "api_key": new_key})
    assert (await admin_client.get("/api/v1/agent/ping", headers=new)).status_code == 200


async def test_delete_agent_cascades_metrics(
    admin_client: httpx.AsyncClient, agent_creds, engine: AsyncEngine
):
    await admin_client.post(
        "/api/v1/metrics", json=make_sample("web-1"), headers=agent_headers(agent_creds)
    )
    assert (await admin_client.delete("/api/v1/agents/web-1")).status_code == 204
    assert (await admin_client.get("/api/v1/agents/web-1")).status_code == 404
    async with engine.connect() as conn:
        count = (await conn.execute(select(func.count()).select_from(MetricSample))).scalar()
    assert count == 0


async def test_agent_overview_includes_latest_metrics(admin_client: httpx.AsyncClient, agent_creds):
    await admin_client.post(
        "/api/v1/metrics", json=make_sample("web-1", cpu=42.0), headers=agent_headers(agent_creds)
    )
    (agent,) = (await admin_client.get("/api/v1/agents")).json()
    assert agent["status"] == "online"
    assert agent["latest"]["cpu_percent"] == 42.0
