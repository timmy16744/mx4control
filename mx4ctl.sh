#!/bin/bash
# Dev wrapper that runs the CLI directly from source (no install required).
# Production: use `mx4ctl` from $PATH after install.sh.
cd "$(dirname "$(readlink -f "$0")")"
exec env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m mx4.cli.main "$@"
