"""Builders for the event payloads pushed over the WebSocket."""

from datetime import datetime
from typing import Any

from app.schemas.alerts import AlertOut


def sample_event(agent_id: str, ts: datetime, summary: dict[str, float | None]) -> dict[str, Any]:
    return {"type": "sample", "agent_id": agent_id, "ts": ts.isoformat(), "summary": summary}


def agent_status_event(agent_id: str, status: str) -> dict[str, Any]:
    return {"type": "agent_status", "agent_id": agent_id, "status": status}


def agents_changed_event() -> dict[str, Any]:
    return {"type": "agents_changed"}


def alert_event(action: str, alert: AlertOut) -> dict[str, Any]:
    return {"type": "alert", "action": action, "alert": alert.model_dump(mode="json")}
