"""WebSocket tests use Starlette's synchronous TestClient (its own event loop)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from tests.conftest import ADMIN, CSRF, make_settings
from tests.factories import make_sample


@pytest.fixture
def sync_client():
    app = create_app(make_settings(), background_jobs=False)
    with TestClient(app, headers=CSRF) as client:
        yield client


def test_live_sample_is_pushed_to_dashboard(sync_client: TestClient):
    sync_client.post("/api/v1/auth/register", json=ADMIN)
    sync_client.post("/api/v1/auth/login", json=ADMIN)
    key = sync_client.post("/api/v1/agents", json={"agent_id": "web-1"}).json()["api_key"]

    with sync_client.websocket_connect("/api/v1/ws") as ws:
        assert ws.receive_json() == {"type": "hello"}
        resp = sync_client.post(
            "/api/v1/metrics",
            json=make_sample("web-1", cpu=12.5),
            headers={"Authorization": f"Bearer {key}", "X-Agent-ID": "web-1"},
        )
        assert resp.status_code == 200
        assert ws.receive_json() == {
            "type": "agent_status",
            "agent_id": "web-1",
            "status": "online",
        }
        event = ws.receive_json()
        assert event["type"] == "sample"
        assert event["summary"]["cpu_percent"] == 12.5


def test_websocket_requires_session(sync_client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc, sync_client.websocket_connect("/api/v1/ws"):
        pass
    assert exc.value.code == 4401


def test_websocket_rejects_foreign_origin(sync_client: TestClient):
    sync_client.post("/api/v1/auth/register", json=ADMIN)
    sync_client.post("/api/v1/auth/login", json=ADMIN)
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        sync_client.websocket_connect("/api/v1/ws", headers={"Origin": "https://evil.example"}),
    ):
        pass
    assert exc.value.code == 1008
