#!/usr/bin/env bash
# Install the InfraWatch agent as a systemd service.
#
#   sudo ./scripts/install-agent.sh --server https://monitor.example.com \
#        --agent-id web-01 --api-key iwk_...
#
# Creates a dedicated unprivileged user, a virtualenv in /opt/infrawatch-agent,
# /etc/infrawatch/agent.env (mode 600) and enables the service.
set -euo pipefail

SERVER="" AGENT_ID="$(hostname -s | tr '[:upper:]' '[:lower:]')" API_KEY="" INTERVAL=5
while [[ $# -gt 0 ]]; do
  case "$1" in
    --server) SERVER="$2"; shift 2 ;;
    --agent-id) AGENT_ID="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --interval) INTERVAL="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ $EUID -eq 0 ]] || { echo "run as root (sudo)" >&2; exit 1; }
[[ -n "$SERVER" && -n "$API_KEY" ]] || { echo "--server and --api-key are required" >&2; exit 2; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX=/opt/infrawatch-agent

id infrawatch &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin infrawatch
python3 -m venv "$PREFIX"
"$PREFIX/bin/pip" install --quiet --upgrade pip
"$PREFIX/bin/pip" install --quiet "$REPO_DIR/agent"

install -d -m 0750 -o root -g infrawatch /etc/infrawatch
umask 077
cat > /etc/infrawatch/agent.env <<CONF
SERVER_URL=$SERVER
AGENT_ID=$AGENT_ID
API_KEY=$API_KEY
COLLECTION_INTERVAL=$INTERVAL
LOG_FORMAT=json
CONF
chown root:infrawatch /etc/infrawatch/agent.env
chmod 0640 /etc/infrawatch/agent.env

install -m 0644 "$REPO_DIR/scripts/infrawatch-agent.service" /etc/systemd/system/infrawatch-agent.service
systemctl daemon-reload
sudo -u infrawatch "$PREFIX/bin/infrawatch-agent" --config /etc/infrawatch/agent.env test || {
  echo "Connectivity test failed; fix the configuration and run: systemctl enable --now infrawatch-agent" >&2
  exit 1
}
systemctl enable --now infrawatch-agent
echo "InfraWatch agent installed. Check it with: systemctl status infrawatch-agent"
