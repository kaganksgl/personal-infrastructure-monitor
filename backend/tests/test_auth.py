import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.models import AuditLog, User
from tests.conftest import ADMIN, CSRF

VIEWER = {"username": "viewer", "password": "another-long-password"}


async def _rows(engine: AsyncEngine, model):  # type: ignore[no-untyped-def]
    async with engine.connect() as conn:
        return (await conn.execute(select(model))).all()


async def test_first_user_becomes_admin_then_registration_closes(client: httpx.AsyncClient):
    status = (await client.get("/api/v1/auth/status")).json()
    assert status == {"registration_open": True, "has_users": False}

    resp = await client.post("/api/v1/auth/register", json=ADMIN)
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"

    resp = await client.post("/api/v1/auth/register", json=VIEWER)
    assert resp.status_code == 403
    assert (await client.get("/api/v1/auth/status")).json()["registration_open"] is False


async def test_password_is_hashed_with_argon2id(client: httpx.AsyncClient, engine: AsyncEngine):
    await client.post("/api/v1/auth/register", json=ADMIN)
    (user,) = await _rows(engine, User)
    assert user.password_hash.startswith("$argon2id$")
    assert ADMIN["password"] not in user.password_hash


async def test_weak_or_malformed_credentials_rejected(client: httpx.AsyncClient):
    short = await client.post("/api/v1/auth/register", json={"username": "bob", "password": "x"})
    assert short.status_code == 422
    bad_name = {"username": "bob'; DROP TABLE users;--", "password": "long-enough-pw"}
    assert (await client.post("/api/v1/auth/register", json=bad_name)).status_code == 422


async def test_login_sets_httponly_session_cookie(client: httpx.AsyncClient):
    await client.post("/api/v1/auth/register", json=ADMIN)
    resp = await client.post("/api/v1/auth/login", json=ADMIN)
    assert resp.status_code == 200
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert (await client.get("/api/v1/auth/me")).json()["username"] == "admin"


async def test_wrong_password_is_rejected_and_audited(
    client: httpx.AsyncClient, engine: AsyncEngine
):
    await client.post("/api/v1/auth/register", json=ADMIN)
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password!"}
    )
    assert resp.status_code == 401
    actions = [row.action for row in await _rows(engine, AuditLog)]
    assert "user.login_failed" in actions


async def test_logout_revokes_session_server_side(client: httpx.AsyncClient):
    await client.post("/api/v1/auth/register", json=ADMIN)
    await client.post("/api/v1/auth/login", json=ADMIN)
    token = client.cookies.get("iw_session")
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    # Replaying the old token must fail even though the client still has it.
    client.cookies.set("iw_session", token, path="/api")
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_state_changing_requests_require_csrf_header(admin_client: httpx.AsyncClient):
    del admin_client.headers["X-Requested-With"]
    resp = await admin_client.post("/api/v1/agents", json={"agent_id": "csrf-test"})
    assert resp.status_code == 403
    admin_client.headers.update(CSRF)


async def test_unauthenticated_requests_are_rejected(client: httpx.AsyncClient):
    for path in ("/api/v1/agents", "/api/v1/alerts", "/api/v1/metrics/x?range=1h"):
        assert (await client.get(path)).status_code == 401


async def test_login_is_rate_limited(client: httpx.AsyncClient):
    creds = {"username": "nobody", "password": "wrong-password!"}
    codes = [(await client.post("/api/v1/auth/login", json=creds)).status_code for _ in range(12)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


async def test_viewer_cannot_perform_admin_actions(client: httpx.AsyncClient, settings):
    settings.allow_registration = True
    await client.post("/api/v1/auth/register", json=ADMIN)
    assert (await client.post("/api/v1/auth/register", json=VIEWER)).json()["role"] == "viewer"
    await client.post("/api/v1/auth/login", json=VIEWER)
    assert (await client.post("/api/v1/agents", json={"agent_id": "x1"})).status_code == 403
    assert (await client.get("/api/v1/system/audit")).status_code == 403
    assert (await client.get("/api/v1/agents")).status_code == 200
