#!/usr/bin/env sh
# mikraw launcher — Unix/macOS
# Runs the venv interpreter relative to this script so it works from any directory.
DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/.venv/bin/python" -m mikraw "$@"
