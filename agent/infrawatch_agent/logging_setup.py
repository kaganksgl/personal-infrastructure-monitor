"""Structured logging for the agent (JSON lines by default, text for humans)."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}
_SENSITIVE = ("api_key", "password", "token", "secret", "authorization")


class _AgentContext(logging.Filter):
    def __init__(self, agent_id: str) -> None:
        super().__init__()
        self.agent_id = agent_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.agent_id = self.agent_id
        return True


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        k: ("***" if any(s in k.lower() for s in _SENSITIVE) else v)
        for k, v in vars(record).items()
        if k not in _STANDARD and not k.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "event": record.getMessage(),
            **_extras(record),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        extras = " ".join(f"{k}={v}" for k, v in _extras(record).items() if k != "agent_id")
        stamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        return (
            f"{stamp} {record.levelname:<7} {record.name}: {record.getMessage()} {extras}".rstrip()
        )


def configure_logging(level: str, fmt: str, agent_id: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    handler.addFilter(_AgentContext(agent_id))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
