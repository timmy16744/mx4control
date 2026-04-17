#!/bin/bash
# Dev wrapper that runs the daemon from source.
cd "$(dirname "$(readlink -f "$0")")"
exec env PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
    LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so \
    /usr/bin/python3 -m mx4.daemon.main "$@"
