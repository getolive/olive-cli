#!/bin/sh

# 🧠 Olive Sandbox Entrypoint Script
## 
## IMPORTANT: Any local modifications (within your project .olive) 
##            will be automatically overwritten anytime the
##            sandbox is rebuilt.
##
#
# This script controls startup behavior for the Olive sandbox container.
# It supports the following modes:
#
#   - daemon: Initializes the container, then launches `olive shell` inside tmux.
#             This ensures tmux becomes PID 1 and keeps the container alive.
#
#   - debug:  Starts a raw bash shell for manual inspection and troubleshooting.
#
#   - any other command: Executes the Olive CLI with the given arguments.
#
# ─────────────────────────────────────────────────────────────
# 🔍 Why we use `tmux` as PID 1 (not `olive --daemon shell`)
#
# Although Olive supports `--daemon shell` mode and manages its own tmux session,
# this approach fails when run as PID 1 in a Docker container — because Olive exits
# immediately after launching tmux, causing the container itself to exit.
#
# By making `tmux` the entrypoint process (PID 1), we ensure the container stays alive
# and can receive commands via `docker exec` or `:sandbox-tty`.
#
# Docker must launch the container with `-dit` to ensure a valid pseudo-TTY.
# If you see errors like:
#   - "stdin is not a terminal"
#   - "open terminal failed"
# …make sure you're using `docker run -dit`.
# ─────────────────────────────────────────────────────────────

set -e

if [ "$1" = "daemon" ]; then
  echo "[sandbox] Starting in daemon mode"

  # ── derive a session id ──────────────────────────────────────────
  if [ -z "$OLIVE_SESSION_ID" ]; then
    if command -v uuidgen >/dev/null 2>&1; then
      export OLIVE_SESSION_ID=$(uuidgen | cut -c1-8)
    else
      export OLIVE_SESSION_ID=$(cat /proc/sys/kernel/random/uuid | cut -c1-8)
    fi
  fi

  # ── per‑daemon sandbox dirs live under home (always writable) ────
  export OLIVE_SANDBOX_DIR="$HOME/.olive/run/sbx/$OLIVE_SESSION_ID"
  mkdir -p "$OLIVE_SANDBOX_DIR/rpc" "$OLIVE_SANDBOX_DIR/result/logs"

  echo "[sandbox] SID=$OLIVE_SESSION_ID  dir=$OLIVE_SANDBOX_DIR"

  . /olive/.venv/bin/activate
  cd /mnt/project
  olive init

  # tmux session name mirrors the SID
  # we need to avoid tripping olive up that this directory isn't a git repo. 
  # or we just need to make it always one if it isn't already. TODO#
  exec tmux new-session  -c /mnt/project  -s "olive-$OLIVE_SESSION_ID" \
    "env OLIVE_SESSION_ID=$OLIVE_SESSION_ID \
    OLIVE_SANDBOX_DIR=$OLIVE_SANDBOX_DIR \
    olive shell"

elif [ "$1" = "debug" ]; then
  echo "[sandbox] Starting in DEBUG mode — dropping to bash shell"
  exec bash

else
  echo "[sandbox] Executing custom command: olive $*"
  . /olive/.venv/bin/activate
  cd /mnt/project
  exec olive "$@"
fi

