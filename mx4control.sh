#!/bin/bash
# MX4Control launcher script
cd /home/timh/projects/mx4control
exec env LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so /usr/bin/python3 -u src/main.py "$@"
