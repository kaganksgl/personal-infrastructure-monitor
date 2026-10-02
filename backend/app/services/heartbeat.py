"""Marks agents offline when they stop reporting."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Agent
from app.services.alerts.engine import AlertEngine
from app.services.alerts.notifier import AlertEvent
from app.services.events import agent_status_event
from app.websocket.hub import Hub

log = logging.getLogger("heartbeat")


async def check_heartbeats(
    db: AsyncSession,
    settings: Settings,
    engine: AlertEngine,
    hub: Hub,
    now: datetime,
    *,
    server_started_at: datetime | None = None,
) -> list[str]:
    window = timedelta(seconds=settings.agent_offline_after_seconds)
    # Startup grace period: after the *backend* was down, every agent's
    # last_seen is stale. Give agents one full window to reconnect before
    # declaring them offline, otherwise a server restart pages for every host.
    if server_started_at is not None and now - server_started_at < window:
        return []
    cutoff = now - window
    stale = (
        await db.execute(
            select(Agent).where(Agent.is_online.is_(True), Agent.last_seen_at < cutoff)
        )
    ).scalars()
    went_offline: list[str] = []
    events: list[AlertEvent] = []
    for agent in stale:
        agent.is_online = False
        went_offline.append(agent.agent_id)
        events += await engine.agent_went_offline(
            db, agent, now, settings.agent_offline_after_seconds
        )
        log.warning("agent.offline", extra={"agent_id": agent.agent_id})
    await db.commit()
    await engine.dispatch(events)
    for agent_id in went_offline:
        hub.publish(agent_status_event(agent_id, "offline"))
    return went_offline
