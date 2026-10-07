#!/usr/bin/env bash
# HOME/XDG must be isolated BEFORE the bus starts and activates dconf-service.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
command -v dconf >/dev/null
command -v dbus-run-session >/dev/null
sandbox="$(mktemp -d)"
trap 'rm -rf -- "$sandbox"' EXIT
export HOME="$sandbox/home"
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state" XDG_CACHE_HOME="$HOME/.cache"
export XDG_RUNTIME_DIR="$sandbox/runtime" PYTHONPYCACHEPREFIX="$sandbox/pycache"
export BIGLINUX_TEST_DCONF="$sandbox"  # conftest refuses a HOME outside it
unset DBUS_SESSION_BUS_ADDRESS DCONF_PROFILE
mkdir -p "$HOME" "$XDG_RUNTIME_DIR"
chmod 700 "$HOME" "$XDG_RUNTIME_DIR"
dbus-run-session -- "$PYTHON" -m pytest tests/test_dconf.py -q "$@"
