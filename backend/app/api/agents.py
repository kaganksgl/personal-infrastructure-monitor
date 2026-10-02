from fastapi import APIRouter, HTTPException, Request, status

from app.auth.dependencies import (
    AdminUser,
    AppSettings,
    AuthenticatedAgent,
    CurrentUser,
    DbSession,
    client_ip,
)
from app.models import Agent
from app.schemas.agents import AgentCreate, AgentCreated, AgentOut
from app.services import agents as agent_service
from app.services import audit
from app.services.events import agents_changed_event

router = APIRouter(tags=["agents"])


async def _load(db: DbSession, agent_id: str) -> Agent:
    agent = await agent_service.get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(db: DbSession, settings: AppSettings, _: CurrentUser) -> list[AgentOut]:
    return await agent_service.list_agents_overview(db, settings)


@router.post("/agents", response_model=AgentCreated, status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: AgentCreate, request: Request, db: DbSession, settings: AppSettings, admin: AdminUser
) -> AgentCreated:
    try:
        agent, key = await agent_service.create_agent(db, body.agent_id, body.display_name, admin)
    except agent_service.AgentExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent ID already registered") from None
    audit.record(db, "agent.created", user=admin, target=agent.agent_id, ip=client_ip(request))
    await db.commit()
    request.app.state.hub.publish(agents_changed_event())
    return AgentCreated(agent=agent_service.to_out(agent, 0, settings), api_key=key)


@router.get("/agents/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str, db: DbSession, settings: AppSettings, _: CurrentUser
) -> AgentOut:
    agent = await _load(db, agent_id)
    counts = await agent_service.active_alert_counts(db)
    return agent_service.to_out(agent, counts.get(agent.id, 0), settings)


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, request: Request, db: DbSession, admin: AdminUser) -> None:
    agent = await _load(db, agent_id)
    request.app.state.alert_engine.forget_agent(agent.id)
    await db.delete(agent)  # metrics, rollups and alerts cascade in the database
    audit.record(db, "agent.deleted", user=admin, target=agent_id, ip=client_ip(request))
    await db.commit()
    request.app.state.hub.publish(agents_changed_event())


@router.post("/agents/{agent_id}/rotate-key", response_model=AgentCreated)
async def rotate_agent_key(
    agent_id: str, request: Request, db: DbSession, settings: AppSettings, admin: AdminUser
) -> AgentCreated:
    agent = await _load(db, agent_id)
    key = agent_service.rotate_key(agent)
    audit.record(db, "agent.key_rotated", user=admin, target=agent_id, ip=client_ip(request))
    await db.commit()
    return AgentCreated(agent=agent_service.to_out(agent, 0, settings), api_key=key)


@router.get("/agent/ping", tags=["agent protocol"])
async def agent_ping(agent: AuthenticatedAgent) -> dict[str, str]:
    """Lets ``infrawatch-agent test`` verify its credentials without sending data."""
    return {"status": "ok", "agent_id": agent.agent_id}
