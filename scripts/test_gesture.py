#!/usr/bin/env python3
"""
Test script for gesture detection.

Run this to verify the gesture button detection works before testing
the full Actions Ring integration.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.gesture_detector import GestureDetector, GestureDirection


def main():
    print()
    print("=" * 60)
    print("  MX4Control - Gesture Detection Test")
    print("=" * 60)
    print()

    detector = GestureDetector()

    # Find device
    device = detector.find_device()
    if not device:
        print("ERROR: No MX Master 4 or compatible mouse found!")
        print()
        print("Make sure your mouse is connected and you have read")
        print("permissions on /dev/input/event* devices.")
        print()
        print("Try adding yourself to the 'input' group:")
        print("  sudo usermod -a -G input $USER")
        print("  (then log out and back in)")
        return 1

    print(f"Found device: {device.name}")
    print(f"Path: {device.path}")
    print()
    print("-" * 60)
    print("Press and hold the gesture button (under your thumb),")
    print("then move the mouse in different directions.")
    print("Release to see the detected gesture.")
    print()
    print("Press Ctrl+C to exit.")
    print("-" * 60)
    print()

    # Set up callbacks
    def on_start():
        print(">>> Gesture STARTED - move mouse in a direction...")

    def on_move(direction: GestureDirection, dx: int, dy: int):
        print(f"    Direction: {direction.name:8s}  (dx={dx:4d}, dy={dy:4d})")

    def on_end(event):
        print(f"<<< Gesture ENDED: {event.direction.name}")
        print(f"    Total movement: dx={event.dx}, dy={event.dy}")
        print(f"    Distance: {event.distance:.1f} pixels")
        print(f"    Duration: {event.end_time - event.start_time:.2f}s")
        print()

    detector.on_gesture_start = on_start
    detector.on_gesture_move = on_move
    detector.on_gesture_end = on_end

    # Start detector
    if not detector.start():
        print("ERROR: Failed to start gesture detector!")
        return 1

    print("Gesture detector running...")
    print()

    try:
        # Keep running until Ctrl+C
        while detector.is_running:
            import time
            time.sleep(0.1)
    except KeyboardInterrupt:
        print()
        print("Stopping...")

    detector.stop()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
