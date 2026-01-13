#!/bin/bash
# MX4Control Launcher
# Runs the application with proper permissions for gesture detection

cd "$(dirname "$0")/src"

# Check if user is in input group
if ! groups | grep -q '\binput\b'; then
    echo "Note: For gesture detection, you need to be in the 'input' group."
    echo "Run: sudo usermod -a -G input $USER"
    echo "Then log out and back in."
    echo ""
    echo "Attempting to run with 'sg input'..."
    exec sg input -c "/usr/bin/python3 main.py"
else
    exec /usr/bin/python3 main.py
fi
