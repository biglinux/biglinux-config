#!/usr/bin/env bash
# Read/write tests must never inherit a real HOME or dconf session.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
sandbox="$(mktemp -d)"
trap 'rm -rf -- "$sandbox"' EXIT
export HOME="$sandbox/home"
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state" XDG_CACHE_HOME="$HOME/.cache"
export XDG_RUNTIME_DIR="$sandbox/runtime" PYTHONPYCACHEPREFIX="$sandbox/pycache"
unset BIGLINUX_TEST_DCONF DBUS_SESSION_BUS_ADDRESS DCONF_PROFILE
mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$HOME" "$XDG_RUNTIME_DIR"
"$PYTHON" -m compileall -q biglinux-config/usr/share/biglinux/biglinux-config tests tools
"$PYTHON" -m pytest tests/ -q "$@"
