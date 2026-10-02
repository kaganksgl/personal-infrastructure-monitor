"""``python -m infrawatch_agent`` starts the agent (same as ``infrawatch-agent start``)."""

import sys

from infrawatch_agent.cli import main

sys.exit(main(sys.argv[1:] or ["start"]))
