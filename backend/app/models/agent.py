from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin


class Agent(TimestampMixin, Base):
    """A monitored machine.

    ``agent_id`` is the human-readable slug used in URLs and by the agent
    itself; ``id`` is the compact surrogate key used by the large metric tables.
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    api_key_hash: Mapped[str] = mapped_column(String(64))
    # First characters of the key, safe to display so users can tell keys apart.
    api_key_prefix: Mapped[str] = mapped_column(String(16))
    system_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    agent_version: Mapped[str | None] = mapped_column(String(32))
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ip: Mapped[str | None] = mapped_column(String(64))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
