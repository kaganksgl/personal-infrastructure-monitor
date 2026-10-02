"""Command-line interface: ``infrawatch-agent {start,status,test,config}``."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from infrawatch_agent import PROTOCOL_VERSION, __version__
from infrawatch_agent.collectors import HostPaths, default_registry
from infrawatch_agent.collectors.host import system_info
from infrawatch_agent.config import AgentConfig, ConfigError, load_config
from infrawatch_agent.logging_setup import configure_logging
from infrawatch_agent.security.redact import insecure_permissions, mask_secret
from infrawatch_agent.state import process_alive, read_state
from infrawatch_agent.transport.client import HttpTransport, Outcome


def _print_kv(rows: list[tuple[str, Any]]) -> None:
    width = max(len(k) for k, _ in rows)
    for key, value in rows:
        print(f"  {key:<{width}}  {value}")


def _transport(config: AgentConfig) -> HttpTransport:
    return HttpTransport(
        config.server_url,
        config.agent_id,
        config.api_key,
        timeout=config.request_timeout,
        verify=config.ca_bundle or config.verify_tls,
    )


def _security_warnings(config: AgentConfig, config_path: Path | None) -> list[str]:
    warnings = []
    if config.sends_key_in_cleartext:
        warnings.append(
            "SERVER_URL uses plain http:// to a remote host: the API key and metrics travel "
            "unencrypted. Put the server behind TLS."
        )
    if config_path and insecure_permissions(config_path):
        warnings.append(f"{config_path} is readable by other users; run: chmod 600 {config_path}")
    if not config.verify_tls:
        warnings.append("VERIFY_TLS=false disables certificate checks (man-in-the-middle risk).")
    return warnings


def cmd_start(config: AgentConfig, args: argparse.Namespace) -> int:
    from infrawatch_agent.main import AgentRunner

    config.validate()
    configure_logging(config.log_level, config.log_format, config.agent_id)
    import logging

    for warning in _security_warnings(config, args.config):
        logging.getLogger("agent").warning("config.insecure", extra={"warning": warning})
    runner = AgentRunner(config)
    if args.once:
        runner.registry.prime()
        time.sleep(1)
        runner.cycle()
        runner.shutdown()
        return 0 if runner.buffer.size() == 0 else 1
    runner.run_forever()
    return 0


def cmd_status(config: AgentConfig, args: argparse.Namespace) -> int:
    state = read_state(config.state_path)
    if state is None:
        print(f"No agent state found at {config.state_path} (has the agent run yet?)")
        return 3
    running = process_alive(int(state.get("pid", 0)))
    last = state.get("last_collection_at")
    age = None
    if last:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
    healthy = running and age is not None and age < config.collection_interval * 3
    print(f"InfraWatch agent {state.get('version')} - {'RUNNING' if running else 'STOPPED'}")
    _print_kv(
        [
            ("Agent ID", state.get("agent_id")),
            ("PID", state.get("pid")),
            ("Server", state.get("server_url")),
            ("Started", state.get("started_at")),
            ("Last collection", f"{last} ({age:.0f}s ago)" if age is not None else "never"),
            ("Last upload", state.get("last_upload_at") or "never"),
            ("Buffered samples", state.get("queue_size")),
            ("Uploaded samples", state.get("samples_uploaded")),
            ("Failed requests", state.get("failed_requests_total")),
            ("Dropped samples", state.get("dropped_samples_total")),
            ("Next retry in", f"{state.get('next_retry_in_seconds', 0)}s"),
            ("Last error", state.get("last_error") or "-"),
        ]
    )
    if args.json:
        print(json.dumps(state, indent=2))
    return 0 if healthy else 1


def cmd_test(config: AgentConfig, args: argparse.Namespace) -> int:
    """Run every collector once, then check server reachability and credentials."""
    paths = HostPaths()
    registry = default_registry(config, paths)
    print("Collectors")
    registry.prime()
    time.sleep(1.0)  # let rate-based collectors observe a real interval
    ok = True
    sample: dict[str, Any] = {}
    for collector in registry.collectors:
        started = time.perf_counter()
        try:
            sample[collector.name] = collector.collect()
            status = "ok"
        except Exception as exc:
            status, ok = f"FAILED ({type(exc).__name__}: {exc})", False
        print(
            f"  {collector.name:<10} {status:<8} {(time.perf_counter() - started) * 1000:7.1f} ms"
        )

    if args.json:
        payload = {"schema_version": PROTOCOL_VERSION, "agent_id": config.agent_id, **sample}
        print(json.dumps({"system_info": system_info(paths), "sample": payload}, indent=2))
    else:
        _print_summary(sample, system_info(paths))

    print("\nServer")
    transport = _transport(config)
    health = transport.health()
    reachable = health.outcome is Outcome.OK
    print(f"  {config.server_url}: {'reachable' if reachable else 'UNREACHABLE ' + health.detail}")
    if reachable and config.api_key:
        ping = transport.ping()
        auth_ok = ping.outcome is Outcome.OK
        print(f"  credentials for '{config.agent_id}': {'valid' if auth_ok else 'REJECTED'}")
        ok = ok and auth_ok
    elif not config.api_key:
        print("  credentials: API_KEY not set")
        ok = False
    transport.close()
    for warning in _security_warnings(config, args.config):
        print(f"  warning: {warning}")
    return 0 if ok and reachable else 1


def _print_summary(sample: dict[str, Any], info: dict[str, Any]) -> None:
    gib = 1024**3
    cpu, mem = sample.get("cpu", {}), sample.get("memory", {})
    temps = [t["current_c"] for t in sample.get("sensors", {}).get("temperatures", [])]
    interfaces = [i["name"] for i in sample.get("network", {}).get("interfaces", [])]
    used, total = mem.get("used_bytes", 0) / gib, mem.get("total_bytes", 0) / gib
    print("\nSummary")
    _print_kv(
        [
            ("Host", f"{info['hostname']} ({info['os_name']}, kernel {info['kernel']})"),
            ("CPU", f"{info.get('cpu_model')}: {cpu.get('usage_percent')}%"),
            ("Load average", f"{cpu.get('load_1m')} {cpu.get('load_5m')} {cpu.get('load_15m')}"),
            ("Memory", f"{used:.1f} / {total:.1f} GiB ({mem.get('usage_percent')}%)"),
            ("Filesystems", len(sample.get("disks", {}).get("filesystems", []))),
            ("Interfaces", ", ".join(interfaces) or "-"),
            ("Sensors", f"{len(temps)}, hottest {max(temps)}°C" if temps else "none available"),
            ("Processes", sample.get("processes", {}).get("total")),
        ]
    )


def cmd_config(config: AgentConfig, args: argparse.Namespace) -> int:
    print(f"Effective configuration (source: {config.source})")
    rows = [
        (key.upper(), mask_secret(str(value)) if key == "api_key" else value)
        for key, value in vars(config).items()
        if key != "source"
    ]
    _print_kv(rows)
    try:
        config.validate()
    except ConfigError as exc:
        print(f"\nInvalid: {exc}")
        return 1
    for warning in _security_warnings(config, args.config):
        print(f"warning: {warning}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infrawatch-agent", description="InfraWatch Linux monitoring agent"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="env-style config file (KEY=value)")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="run the agent in the foreground")
    start.add_argument(
        "--once", action="store_true", help="collect and upload one sample, then exit"
    )
    status = sub.add_parser("status", help="show the state of a running agent")
    status.add_argument("--json", action="store_true")
    test = sub.add_parser("test", help="run collectors once and verify server connectivity")
    test.add_argument("--json", action="store_true", help="print the full collected payload")
    sub.add_parser("config", help="print the effective configuration (secrets masked)")
    return parser


COMMANDS = {"start": cmd_start, "status": cmd_status, "test": cmd_test, "config": cmd_config}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        return COMMANDS[args.command](config, args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
