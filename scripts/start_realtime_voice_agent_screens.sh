#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CONDA_ENV="${CONDA_ENV:-Tanyue}"
CONDA_BASE="${CONDA_BASE:-$(conda info --base 2>/dev/null || true)}"
CONDA_SH="${CONDA_SH:-${CONDA_BASE}/etc/profile.d/conda.sh}"

SCREEN_PREFIX="${TANYUE_SCREEN_PREFIX:-tanyue}"
LOG_DIR="${TANYUE_SCREEN_LOG_DIR:-$PROJECT_ROOT/output/screen_logs}"

LIVEKIT_URL="${LIVEKIT_URL:-ws://127.0.0.1:7880}"
LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-devkey}"
LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-devsecret}"
TANYUE_BRIDGE_HOST="${TANYUE_BRIDGE_HOST:-127.0.0.1}"
TANYUE_BRIDGE_PORT="${TANYUE_BRIDGE_PORT:-8893}"
TANYUE_WEB_HOST="${TANYUE_WEB_HOST:-127.0.0.1}"
TANYUE_WEB_PORT="${TANYUE_WEB_PORT:-8894}"

SESSIONS=(
  "livekit"
  "character_bridge"
  "agent_worker"
  "web"
)

usage() {
  cat <<EOF
Usage: $(basename "$0") [start|stop|restart|status|logs]

Starts the realtime voice Agent stack in 4 detached screen sessions:
  ${SCREEN_PREFIX}-livekit
  ${SCREEN_PREFIX}-character_bridge
  ${SCREEN_PREFIX}-agent_worker
  ${SCREEN_PREFIX}-web

Environment overrides:
  CONDA_ENV=$CONDA_ENV
  TANYUE_SCREEN_PREFIX=$SCREEN_PREFIX
  TANYUE_SCREEN_LOG_DIR=$LOG_DIR
  LIVEKIT_URL=$LIVEKIT_URL
  LIVEKIT_API_KEY=$LIVEKIT_API_KEY
  LIVEKIT_API_SECRET=$LIVEKIT_API_SECRET
  TANYUE_BRIDGE_HOST=$TANYUE_BRIDGE_HOST
  TANYUE_BRIDGE_PORT=$TANYUE_BRIDGE_PORT
  TANYUE_WEB_HOST=$TANYUE_WEB_HOST
  TANYUE_WEB_PORT=$TANYUE_WEB_PORT

Remote browser access example:
  TANYUE_WEB_HOST=0.0.0.0 $(basename "$0") restart

Attach to a session:
  screen -r ${SCREEN_PREFIX}-agent_worker
Detach from a session:
  Ctrl-a d
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing command: $cmd" >&2
    exit 1
  fi
}

session_name() {
  printf "%s-%s" "$SCREEN_PREFIX" "$1"
}

is_running() {
  local name
  name="$(session_name "$1")"
  screen -ls | grep -q "[.]${name}[[:space:]]"
}

require_docker_access() {
  require_cmd docker
  if ! docker info >/dev/null 2>&1; then
    cat >&2 <<EOF
docker is installed, but this user cannot talk to the Docker daemon.

Fix once, then log out and back in:
  sudo usermod -aG docker "$USER"

Current user groups:
  $(id)
EOF
    exit 1
  fi
}

write_runner() {
  local key="$1"
  local body="$2"
  local runner="$LOG_DIR/${key}.runner.sh"

  mkdir -p "$LOG_DIR"
  cat >"$runner" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$PROJECT_ROOT"

if [ ! -f "$CONDA_SH" ]; then
  echo "conda activation script not found: $CONDA_SH" >&2
  exit 1
fi

source "$CONDA_SH"
conda activate "$CONDA_ENV"

set -a
[ -f "$PROJECT_ROOT/.env" ] && source "$PROJECT_ROOT/.env"
[ -f "$PROJECT_ROOT/voice/.env" ] && source "$PROJECT_ROOT/voice/.env"
set +a

export LIVEKIT_URL="\${LIVEKIT_URL:-$LIVEKIT_URL}"
export LIVEKIT_API_KEY="\${LIVEKIT_API_KEY:-$LIVEKIT_API_KEY}"
export LIVEKIT_API_SECRET="\${LIVEKIT_API_SECRET:-$LIVEKIT_API_SECRET}"
export TANYUE_CHARACTER_BRIDGE_URL="\${TANYUE_CHARACTER_BRIDGE_URL:-http://127.0.0.1:$TANYUE_BRIDGE_PORT/events}"
export PYTHONUNBUFFERED=1

echo "[\$(date '+%F %T')] starting $key"
$body
EOF
  chmod +x "$runner"
  printf "%s" "$runner"
}

start_screen() {
  local key="$1"
  local body="$2"
  local name log runner

  name="$(session_name "$key")"
  log="$LOG_DIR/${key}.log"

  if is_running "$key"; then
    echo "already running: $name"
    return 0
  fi

  runner="$(write_runner "$key" "$body")"
  : >"$log"
  screen -L -Logfile "$log" -dmS "$name" "$runner"
  echo "started: $name"
  echo "  log: $log"
}

start_all() {
  require_cmd screen
  require_cmd conda
  require_docker_access

  mkdir -p "$LOG_DIR"
  start_screen "livekit" 'cd LiveKit; exec docker compose up'
  start_screen "character_bridge" 'exec python character/scripts/character_bridge.py --host "'"$TANYUE_BRIDGE_HOST"'" --port "'"$TANYUE_BRIDGE_PORT"'"'
  start_screen "agent_worker" 'exec python tanyue_agent.py start'
  start_screen "web" 'exec python tanyue_agent.py web --host "'"$TANYUE_WEB_HOST"'" --port "'"$TANYUE_WEB_PORT"'"'

  echo
  status_all
  echo
  echo "Web UI: http://$TANYUE_WEB_HOST:$TANYUE_WEB_PORT"
  echo "Logs:   $LOG_DIR"
}

stop_all() {
  require_cmd screen

  local key name
  for key in "web" "agent_worker" "character_bridge" "livekit"; do
    name="$(session_name "$key")"
    if is_running "$key"; then
      screen -S "$name" -X quit || true
      echo "stopped: $name"
    else
      echo "not running: $name"
    fi
  done

  if command -v docker >/dev/null 2>&1 && [ -f "$PROJECT_ROOT/LiveKit/docker-compose.yml" ]; then
    (cd "$PROJECT_ROOT/LiveKit" && docker compose down) || true
  fi
}

status_all() {
  require_cmd screen

  echo "screen sessions:"
  screen -ls || true

  if command -v docker >/dev/null 2>&1 && [ -f "$PROJECT_ROOT/LiveKit/docker-compose.yml" ]; then
    echo
    echo "LiveKit docker compose:"
    (cd "$PROJECT_ROOT/LiveKit" && docker compose ps) || true
  fi
}

logs_all() {
  local key log
  for key in "${SESSIONS[@]}"; do
    log="$LOG_DIR/${key}.log"
    echo
    echo "===== $key: $log ====="
    if [ -f "$log" ]; then
      tail -n 80 "$log"
    else
      echo "no log yet"
    fi
  done
}

main() {
  local action="${1:-start}"
  case "$action" in
    start)
      start_all
      ;;
    stop)
      stop_all
      ;;
    restart)
      stop_all
      start_all
      ;;
    status)
      status_all
      ;;
    logs)
      logs_all
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "unknown action: $action" >&2
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
