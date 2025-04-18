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
  . /olive/.venv/bin/activate
  cd /mnt/project
  olive init
  echo "[sandbox] Launching Olive shell inside tmux (PID 1)"
  exec tmux new-session -s default "olive shell"

elif [ "$1" = "debug" ]; then
  echo "[sandbox] Starting in DEBUG mode — dropping to bash shell"
  exec bash

else
  echo "[sandbox] Executing custom command: olive $*"
  . /olive/.venv/bin/activate
  cd /mnt/project
  exec olive "$@"
fi

