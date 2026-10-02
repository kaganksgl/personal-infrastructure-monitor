from pathlib import Path

import pytest

from infrawatch_agent.cli import main
from infrawatch_agent.config import ConfigError, load_config
from infrawatch_agent.config.settings import AgentConfig
from infrawatch_agent.security.redact import insecure_permissions, mask_secret, redact_cmdline


def test_env_overrides_file(tmp_path: Path):
    cfg = tmp_path / "agent.env"
    cfg.write_text('# comment\nSERVER_URL="https://mon.example.com/"\nCOLLECTION_INTERVAL=10\n')
    config = load_config(cfg, environ={"COLLECTION_INTERVAL": "2", "API_KEY": "k"})
    assert config.server_url == "https://mon.example.com"
    assert config.collection_interval == 2.0
    assert config.api_key == "k"
    assert "env" in config.source and "file" in config.source


def test_invalid_values_are_reported(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_config(environ={"COLLECTION_INTERVAL": "fast"})
    with pytest.raises(ConfigError):
        AgentConfig(agent_id="Bad ID", api_key="k").validate()
    with pytest.raises(ConfigError):
        AgentConfig(api_key="").validate()
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.env", environ={})


def test_cleartext_detection():
    assert AgentConfig(server_url="http://10.0.0.5:8080").sends_key_in_cleartext
    assert not AgentConfig(server_url="http://localhost:8080").sends_key_in_cleartext
    assert not AgentConfig(server_url="https://mon.example.com").sends_key_in_cleartext


def test_api_key_never_appears_in_repr():
    assert "supersecret" not in repr(AgentConfig(api_key="iwk_supersecret"))
    assert mask_secret("iwk_supersecretvalue") == "iwk_supe…"


@pytest.mark.parametrize(
    ("cmdline", "leak"),
    [
        ("mysql -u root --password=hunter2 db", "hunter2"),
        ("app --api-key abc123def", "abc123def"),
        ("psql postgres://admin:s3cr3t@db:5432/x", "s3cr3t"),
        ("env DB_PASSWORD=topsecret ./run", "topsecret"),
        ("curl -H token=xyz", "xyz"),
    ],
)
def test_cmdline_secrets_are_redacted(cmdline: str, leak: str):
    redacted = redact_cmdline(cmdline)
    assert leak not in redacted and "***" in redacted


def test_harmless_cmdline_is_unchanged():
    assert redact_cmdline("python -m http.server 8000") == "python -m http.server 8000"


def test_world_readable_config_is_flagged(tmp_path: Path):
    cfg = tmp_path / "agent.env"
    cfg.write_text("API_KEY=x\n")
    cfg.chmod(0o644)
    assert insecure_permissions(cfg)
    cfg.chmod(0o640)
    assert not insecure_permissions(cfg)


def test_cli_version_and_config(capsys, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "1.0.0" in capsys.readouterr().out

    monkeypatch.setenv("API_KEY", "iwk_abcdefghijklmnop")
    monkeypatch.setenv("SERVER_URL", "http://localhost:8080")
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "iwk_abcd…" in out and "iwk_abcdefghijklmnop" not in out


def test_cli_status_without_state(capsys, monkeypatch, tmp_path: Path):
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "none.json"))
    assert main(["status"]) == 3
