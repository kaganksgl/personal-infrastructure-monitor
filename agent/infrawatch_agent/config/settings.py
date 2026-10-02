"""Agent configuration.

Precedence (lowest to highest): built-in defaults, an env-style config file
(``--config``, ``$INFRAWATCH_CONFIG`` or ``/etc/infrawatch/agent.env``), then
process environment variables. The file format is the same ``KEY=value``
syntax systemd's ``EnvironmentFile=`` uses, so one file serves both.
"""

import os
import re
import socket
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/etc/infrawatch/agent.env")
_AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")


class ConfigError(ValueError):
    pass


def _state_dir() -> Path:
    # Follows the XDG base-directory spec; systemd's StateDirectory= sets
    # $STATE_DIRECTORY, which takes priority when running as a service.
    if os.environ.get("STATE_DIRECTORY"):
        return Path(os.environ["STATE_DIRECTORY"])
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "infrawatch"


def default_agent_id() -> str:
    slug = re.sub(r"[^a-z0-9._-]", "-", socket.gethostname().lower()).strip("-.")
    return slug if _AGENT_ID_RE.match(slug) else "linux-host"


@dataclass(frozen=True)
class AgentConfig:
    server_url: str = "http://localhost:8080"
    agent_id: str = field(default_factory=default_agent_id)
    api_key: str = field(default="", repr=False)
    collection_interval: float = 5.0
    buffer_size: int = 1000
    buffer_path: Path = field(default_factory=lambda: _state_dir() / "buffer.db")
    state_path: Path = field(default_factory=lambda: _state_dir() / "state.json")
    batch_size: int = 50
    request_timeout: float = 10.0
    max_backoff: float = 300.0
    verify_tls: bool = True
    ca_bundle: str = ""
    top_processes: int = 10
    collect_cmdline: bool = True
    net_exclude: str = r"^(lo|veth.*|br-.*|docker\d+|virbr\d+(-nic)?|cni\d+|flannel.*)$"
    log_level: str = "INFO"
    log_format: str = "json"
    source: str = "defaults"

    def validate(self, *, require_key: bool = True) -> None:
        if not self.server_url.startswith(("http://", "https://")):
            raise ConfigError("SERVER_URL must start with http:// or https://")
        if not _AGENT_ID_RE.match(self.agent_id):
            raise ConfigError(
                "AGENT_ID must be 2-63 chars of lowercase letters, digits, '.', '_' or '-'"
            )
        if require_key and not self.api_key:
            raise ConfigError("API_KEY is not set (create the agent in the dashboard first)")
        if not 1 <= self.collection_interval <= 3600:
            raise ConfigError("COLLECTION_INTERVAL must be between 1 and 3600 seconds")
        if self.buffer_size < 1 or self.batch_size < 1:
            raise ConfigError("BUFFER_SIZE and BATCH_SIZE must be positive")
        try:
            re.compile(self.net_exclude)
        except re.error as exc:
            raise ConfigError(f"NET_EXCLUDE is not a valid regex: {exc}") from exc

    @property
    def sends_key_in_cleartext(self) -> bool:
        local = re.match(r"^http://(localhost|127\.|\[::1\])", self.server_url)
        return self.server_url.startswith("http://") and not local


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ConfigError(f"{path}:{lineno}: expected KEY=value")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip().upper()] = value
    return values


def _coerce(name: str, raw: str, current: object) -> object:
    try:
        if isinstance(current, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(current, int):
            return int(raw)
        if isinstance(current, float):
            return float(raw)
        if isinstance(current, Path):
            return Path(raw).expanduser()
    except ValueError as exc:
        raise ConfigError(f"{name.upper()}: invalid value {raw!r}") from exc
    return raw


def load_config(
    config_file: Path | None = None, environ: dict[str, str] | None = None
) -> AgentConfig:
    environ = dict(os.environ) if environ is None else environ
    path = config_file or (
        Path(environ["INFRAWATCH_CONFIG"]) if "INFRAWATCH_CONFIG" in environ else None
    )
    if path is None and DEFAULT_CONFIG_PATH.exists():
        path = DEFAULT_CONFIG_PATH
    file_values: dict[str, str] = {}
    if path is not None:
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        file_values = parse_env_file(path)

    defaults = AgentConfig()
    overrides: dict[str, object] = {}
    sources = []
    for f in fields(AgentConfig):
        if f.name == "source":
            continue
        key = f.name.upper()
        if key in environ:
            overrides[f.name] = _coerce(f.name, environ[key], getattr(defaults, f.name))
            sources.append("env")
        elif key in file_values:
            overrides[f.name] = _coerce(f.name, file_values[key], getattr(defaults, f.name))
            sources.append("file")
    source = " + ".join(sorted(set(sources))) or "defaults"
    if path is not None:
        source += f" ({path})"
    server_url = str(overrides.get("server_url", defaults.server_url)).rstrip("/")
    overrides["server_url"] = server_url
    return AgentConfig(**overrides, source=source)  # type: ignore[arg-type]
