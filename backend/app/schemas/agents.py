from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import AgentId, ApiModel, WireModel

AgentStatus = Literal["online", "warning", "offline", "pending"]


class AgentCreate(WireModel):
    agent_id: AgentId
    display_name: str | None = Field(default=None, max_length=128)


class AgentOut(ApiModel):
    agent_id: str
    display_name: str
    status: AgentStatus
    api_key_prefix: str
    agent_version: str | None
    system_info: dict[str, Any] | None
    last_seen_at: datetime | None
    created_at: datetime
    active_alerts: int = 0
    # Most recent scalar metrics, for fleet overview tables.
    latest: dict[str, float | None] | None = None


class AgentCreated(ApiModel):
    agent: AgentOut
    # Returned exactly once; only its hash is stored.
    api_key: str
