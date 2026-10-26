#!/bin/sh
# Keep this wrapper beside downloader.py; configuration is in config.json.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/downloader.py" "$@"
