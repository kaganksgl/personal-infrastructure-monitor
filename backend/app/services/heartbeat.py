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
    db: AsyncSession, settings: Settings, engine: AlertEngine, hub: Hub, now: datetime
) -> list[str]:
    cutoff = now - timedelta(seconds=settings.agent_offline_after_seconds)
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
