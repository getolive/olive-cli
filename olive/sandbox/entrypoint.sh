#!/usr/bin/env bash
# Olive Sandbox Entrypoint
#   *PID-1 is `tini`; this script is PID-2*

set -euo pipefail

MODE=${1:-daemon}

# Default project location inside the container
PROJECT_ROOT=${PROJECT_ROOT:-/mnt/project}
cd "$PROJECT_ROOT"

# -------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------
make_runtime_dirs() {
  mkdir -p "$OLIVE_SANDBOX_DIR"/{rpc,result/logs}
}

# -------------------------------------------------------------------
# modes
# -------------------------------------------------------------------
case "$MODE" in
  daemon)
    echo "[sandbox] ↪ daemon mode"

    # Honour a host-supplied SID, otherwise make a short random one
    SID=${OLIVE_SESSION_ID:-$(python - <<'PY'
import uuid, sys; sys.stdout.write(uuid.uuid4().hex[:8])
PY
)}
    export OLIVE_SESSION_ID="$SID"
    export OLIVE_SANDBOX_DIR="${PROJECT_ROOT}/.olive/run/sbx/${SID}"

    make_runtime_dirs

    # Initialise project (no-op if already done)
    olive init || true

    if command -v tmux >/dev/null 2>&1; then
      exec tmux -q new-session -s "olive-${SID}" -c "$PROJECT_ROOT" \
           "env OLIVE_SESSION_ID=${SID} OLIVE_SANDBOX_DIR=${OLIVE_SANDBOX_DIR} olive shell"
    else
      echo "[sandbox] tmux unavailable ➜ falling back to foreground shell"
      exec env OLIVE_SESSION_ID="$SID" OLIVE_SANDBOX_DIR="$OLIVE_SANDBOX_DIR" olive shell
    fi
    ;;

  debug)
    echo "[sandbox] ↪ debug shell"
    exec bash
    ;;

  *)
    echo "[sandbox] ↪ olive $*"
    shift || true       # drop the first arg (MODE)
    exec olive "$@"
    ;;
esac
