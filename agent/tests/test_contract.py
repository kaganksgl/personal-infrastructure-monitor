"""Contract test: a real agent sample must satisfy the backend's wire schema.

Catches protocol drift between the two components. Skipped when the backend
code or its dependencies are not available (e.g. the agent packaged alone).
"""

import sys
from pathlib import Path

import pytest

from infrawatch_agent.collectors import HostPaths
from infrawatch_agent.collectors.host import system_info
from infrawatch_agent.config import AgentConfig
from infrawatch_agent.main import AgentRunner
from infrawatch_agent.transport.buffer import SampleBuffer

BACKEND = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture
def backend_schemas():
    if not BACKEND.exists():
        pytest.skip("backend source not available")
    sys.path.insert(0, str(BACKEND))
    try:
        from app.schemas import metrics
    except ImportError as exc:
        pytest.skip(f"backend dependencies missing: {exc}")
    finally:
        sys.path.remove(str(BACKEND))
    return metrics


def test_real_sample_matches_backend_schema(backend_schemas, config: AgentConfig):
    runner = AgentRunner(config, buffer=SampleBuffer(":memory:", 10))
    runner.registry.prime()
    sample = runner.collect_once()
    batch = backend_schemas.MetricBatchIn.model_validate(
        {"agent_id": config.agent_id, "system_info": system_info(HostPaths()), "samples": [sample]}
    )
    assert batch.samples[0].cpu.logical_cores >= 1
    assert sample["agent"]["collector_errors"] == []
