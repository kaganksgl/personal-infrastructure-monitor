"""Small JSON status file so ``infrawatch-agent status`` can inspect a running agent."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentState:
    pid: int
    version: str
    agent_id: str
    server_url: str
    started_at: str
    last_collection_at: str | None = None
    last_upload_at: str | None = None
    last_error: str | None = None
    queue_size: int = 0
    samples_collected: int = 0
    samples_uploaded: int = 0
    failed_requests_total: int = 0
    dropped_samples_total: int = 0
    next_retry_in_seconds: float = 0.0


def write_state(path: Path, state: AgentState) -> None:
    """Atomic write (temp file + rename) so readers never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-")
    with os.fdopen(fd, "w") as fh:
        json.dump(asdict(state), fh, indent=2)
    os.replace(tmp, path)


def read_state(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    return True
