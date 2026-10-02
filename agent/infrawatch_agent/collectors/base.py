"""Collector interface and fault-isolating registry."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger("collectors")


@dataclass(frozen=True)
class HostPaths:
    """Filesystem roots, injectable so collectors can be tested against fixtures."""

    proc: Path = Path("/proc")
    sys: Path = Path("/sys")
    etc: Path = Path("/etc")


class Collector(Protocol):
    #: Key of this collector's section in the sample payload.
    name: str

    def prime(self) -> None:
        """Take a baseline reading so the first real sample can compute rates."""

    def collect(self) -> Any:
        """Return this collector's section of the payload."""


@dataclass
class CollectionResult:
    sections: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class CollectorRegistry:
    """Runs every collector; one failing collector never takes down the rest."""

    def __init__(self, collectors: list[Collector]) -> None:
        self.collectors = collectors

    def prime(self) -> None:
        for collector in self.collectors:
            try:
                collector.prime()
            except Exception:
                log.warning("collector.prime_failed", extra={"collector": collector.name})

    def collect(self) -> CollectionResult:
        started = time.perf_counter()
        result = CollectionResult(sections={})
        for collector in self.collectors:
            try:
                result.sections[collector.name] = collector.collect()
            except Exception as exc:
                result.errors.append(collector.name)
                log.warning(
                    "collector.failed",
                    extra={"collector": collector.name, "error": f"{type(exc).__name__}: {exc}"},
                )
        result.duration_ms = (time.perf_counter() - started) * 1000
        return result


def read_text(path: Path, default: str | None = None) -> str | None:
    """Read a small /proc or /sys file; missing or unreadable files yield ``default``."""
    try:
        return path.read_text().strip()
    except (OSError, UnicodeDecodeError):
        return default


def read_int(path: Path) -> int | None:
    text = read_text(path)
    try:
        return int(text) if text is not None else None
    except ValueError:
        return None
