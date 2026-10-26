#!/bin/sh
# Same download workflow, with the optional Docker cleaner enabled.
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$SCRIPT_DIR/downloader.py" --clean "$@"
