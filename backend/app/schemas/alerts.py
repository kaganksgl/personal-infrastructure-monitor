from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.metrics_catalog import METRIC_NAMES
from app.schemas.common import AgentId, ApiModel, WireModel

Severity = Literal["info", "warning", "critical"]
AlertMetric = str  # validated against the catalog below
OFFLINE_METRIC = "agent_offline"


def _validate_metric(value: str) -> str:
    if value != OFFLINE_METRIC and value not in METRIC_NAMES:
        raise ValueError(f"unknown metric '{value}'")
    return value


class AlertRuleIn(WireModel):
    name: str = Field(min_length=1, max_length=128)
    metric: str
    operator: Literal[">", "<"] = ">"
    threshold: float = 0
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    severity: Severity = "warning"
    enabled: bool = True
    agent_id: AgentId | None = None

    _check_metric = field_validator("metric")(_validate_metric)


class AlertRuleUpdate(WireModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    threshold: float | None = None
    operator: Literal[">", "<"] | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    severity: Severity | None = None
    enabled: bool | None = None


class AlertRuleOut(ApiModel):
    id: int
    name: str
    metric: str
    operator: str
    threshold: float
    duration_seconds: int
    severity: Severity
    enabled: bool
    agent_id: str | None
    created_at: datetime


class AlertOut(ApiModel):
    id: int
    agent_id: str
    rule_id: int | None
    rule_name: str
    metric: str
    severity: Severity
    status: Literal["firing", "resolved"]
    message: str
    value: float | None
    threshold: float | None
    started_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by: str | None
