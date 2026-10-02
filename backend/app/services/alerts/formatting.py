"""Human-readable alert messages."""

from app.metrics_catalog import METRICS, Unit
from app.models import AlertRule


def format_value(metric: str, value: float) -> str:
    definition = METRICS.get(metric)
    unit = definition.unit if definition else None
    if unit == Unit.PERCENT:
        return f"{value:.1f}%"
    if unit == Unit.CELSIUS:
        return f"{value:.1f}°C"
    if unit in (Unit.BYTES, Unit.BYTES_PER_SEC):
        suffix = "/s" if unit == Unit.BYTES_PER_SEC else ""
        for prefix in ("B", "KiB", "MiB", "GiB", "TiB"):
            if abs(value) < 1024:
                return f"{value:.1f} {prefix}{suffix}"
            value /= 1024
        return f"{value:.1f} PiB{suffix}"
    if unit == Unit.PER_SEC:
        return f"{value:.1f}/s"
    return f"{value:.2f}"


def threshold_message(rule: AlertRule, value: float) -> str:
    label = METRICS[rule.metric].label if rule.metric in METRICS else rule.metric
    sustained = f" for {rule.duration_seconds}s" if rule.duration_seconds else ""
    return (
        f"{label} is {format_value(rule.metric, value)} "
        f"(threshold {rule.operator} {format_value(rule.metric, rule.threshold)}{sustained})"
    )


def offline_message(agent_name: str, seconds: int) -> str:
    return f"{agent_name} has not reported for more than {seconds}s"
