"""Integration test fixtures.

Tests run against a real PostgreSQL (``TEST_DATABASE_URL``) because the
backend relies on PostgreSQL features (JSONB, date_bin, percentile_cont,
partial unique indexes, ON CONFLICT) that an in-memory substitute would not
exercise. ``make test`` starts a disposable database automatically.
"""

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import Settings
from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://infrawatch:testpass@127.0.0.1:5433/infrawatch_test",
)
CSRF = {"X-Requested-With": "infrawatch"}
ADMIN = {"username": "admin", "password": "correct-horse-battery"}
_TABLES = "users, agents, metric_samples, metric_rollups, alerts, audit_logs, user_sessions"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": TEST_DATABASE_URL,
        "environment": "test",
        "cookie_secure": False,  # the test client talks plain HTTP
        "log_level": "WARNING",
        "db_pool_size": 5,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> Iterator[None]:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    cfg.attributes["database_url"] = TEST_DATABASE_URL
    try:
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    except OSError as exc:
        pytest.exit(f"PostgreSQL not reachable at TEST_DATABASE_URL ({exc}). Run `make test-db`.")
    yield


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(TEST_DATABASE_URL)
    async with eng.begin() as conn:
        # Snapshot the seeded default rules so each test can start from them.
        await conn.execute(text("DROP TABLE IF EXISTS _seed_rules"))
        await conn.execute(text("CREATE TABLE _seed_rules AS SELECT * FROM alert_rules"))
    yield eng
    await eng.dispose()


@pytest.fixture(autouse=True)
async def clean_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_TABLES}, alert_rules RESTART IDENTITY CASCADE"))
        await conn.execute(text("INSERT INTO alert_rules SELECT * FROM _seed_rules"))
        await conn.execute(
            text("SELECT setval('alert_rules_id_seq', (SELECT max(id) FROM alert_rules))")
        )


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[Any]:
    application = create_app(settings, background_jobs=False)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", headers=CSRF
    ) as c:
        yield c


@pytest.fixture
async def admin_client(client: httpx.AsyncClient) -> httpx.AsyncClient:
    assert (await client.post("/api/v1/auth/register", json=ADMIN)).status_code == 201
    assert (await client.post("/api/v1/auth/login", json=ADMIN)).status_code == 200
    return client


@pytest.fixture
async def agent_creds(admin_client: httpx.AsyncClient) -> dict[str, str]:
    resp = await admin_client.post("/api/v1/agents", json={"agent_id": "web-1"})
    assert resp.status_code == 201
    return {"agent_id": "web-1", "api_key": resp.json()["api_key"]}


def agent_headers(creds: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {creds['api_key']}", "X-Agent-ID": creds["agent_id"]}
