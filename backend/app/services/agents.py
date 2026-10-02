"""Agent registry: registration, key rotation, status and fleet overview."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import new_api_key
from app.config import Settings
from app.models import Agent, Alert, MetricSample, User
from app.schemas.agents import AgentOut, AgentStatus

OVERVIEW_METRICS = (
    "cpu_percent",
    "memory_percent",
    "disk_percent_max",
    "net_rx_bps",
    "net_tx_bps",
    "temperature_max_c",
    "load_1m",
)


class AgentExistsError(Exception):
    pass


def compute_status(
    agent: Agent, active_alerts: int, settings: Settings, now: datetime
) -> AgentStatus:
    if agent.last_seen_at is None:
        return "pending"
    stale = agent.last_seen_at < now - timedelta(seconds=settings.agent_offline_after_seconds)
    if stale or not agent.is_online:
        return "offline"
    return "warning" if active_alerts else "online"


async def create_agent(
    db: AsyncSession, agent_id: str, display_name: str | None, creator: User
) -> tuple[Agent, str]:
    exists = await db.execute(select(Agent.id).where(Agent.agent_id == agent_id))
    if exists.first() is not None:
        raise AgentExistsError
    key, key_hash, prefix = new_api_key()
    agent = Agent(
        agent_id=agent_id,
        display_name=display_name or agent_id,
        api_key_hash=key_hash,
        api_key_prefix=prefix,
        created_by_id=creator.id,
    )
    db.add(agent)
    await db.flush()
    return agent, key


def rotate_key(agent: Agent) -> str:
    key, key_hash, prefix = new_api_key()
    agent.api_key_hash = key_hash
    agent.api_key_prefix = prefix
    return key


async def get_agent(db: AsyncSession, agent_id: str) -> Agent | None:
    return (await db.execute(select(Agent).where(Agent.agent_id == agent_id))).scalar_one_or_none()


async def active_alert_counts(db: AsyncSession) -> dict[int, int]:
    rows = await db.execute(
        select(Alert.agent_pk, func.count())
        .where(Alert.status == "firing")
        .group_by(Alert.agent_pk)
    )
    return {agent_pk: count for agent_pk, count in rows}


async def list_agents_overview(db: AsyncSession, settings: Settings) -> list[AgentOut]:
    # LATERAL join: one index lookup per agent on the (agent_pk, ts) primary
    # key for its newest sample, instead of scanning the samples table.
    latest = (
        select(*(getattr(MetricSample, m) for m in OVERVIEW_METRICS))
        .where(MetricSample.agent_pk == Agent.id)
        .order_by(MetricSample.ts.desc())
        .limit(1)
        .lateral("latest")
    )
    rows = await db.execute(
        select(Agent, latest).outerjoin(latest, true()).order_by(Agent.display_name)
    )
    counts = await active_alert_counts(db)
    now = datetime.now(UTC)
    result = []
    for row in rows:
        agent: Agent = row[0]
        values = {m: getattr(row, m) for m in OVERVIEW_METRICS}
        has_data = any(v is not None for v in values.values())
        result.append(
            to_out(agent, counts.get(agent.id, 0), settings, now, values if has_data else None)
        )
    return result


def to_out(
    agent: Agent,
    active_alerts: int,
    settings: Settings,
    now: datetime | None = None,
    latest: dict[str, float | None] | None = None,
) -> AgentOut:
    now = now or datetime.now(UTC)
    return AgentOut(
        agent_id=agent.agent_id,
        display_name=agent.display_name,
        status=compute_status(agent, active_alerts, settings, now),
        api_key_prefix=agent.api_key_prefix,
        agent_version=agent.agent_version,
        system_info=agent.system_info,
        last_seen_at=agent.last_seen_at,
        created_at=agent.created_at,
        active_alerts=active_alerts,
        latest=latest,
    )
