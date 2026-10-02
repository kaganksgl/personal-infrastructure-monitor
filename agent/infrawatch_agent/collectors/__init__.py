from typing import TYPE_CHECKING

from infrawatch_agent.collectors.base import Collector, CollectorRegistry, HostPaths

if TYPE_CHECKING:
    from infrawatch_agent.config import AgentConfig

__all__ = ["Collector", "CollectorRegistry", "HostPaths", "default_registry"]


def default_registry(config: "AgentConfig", paths: HostPaths | None = None) -> CollectorRegistry:
    from infrawatch_agent.collectors.cpu import CpuCollector
    from infrawatch_agent.collectors.disk import DiskCollector
    from infrawatch_agent.collectors.host import HostCollector
    from infrawatch_agent.collectors.memory import MemoryCollector
    from infrawatch_agent.collectors.network import NetworkCollector
    from infrawatch_agent.collectors.processes import ProcessCollector
    from infrawatch_agent.collectors.sensors import SensorCollector

    paths = paths or HostPaths()
    return CollectorRegistry(
        [
            CpuCollector(paths),
            MemoryCollector(paths),
            DiskCollector(paths),
            NetworkCollector(paths, exclude=config.net_exclude),
            SensorCollector(paths),
            ProcessCollector(top_n=config.top_processes, cmdline=config.collect_cmdline),
            HostCollector(paths),
        ]
    )
