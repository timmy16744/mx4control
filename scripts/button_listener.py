#!/usr/bin/env python3
"""
MX Master 4 Button Event Listener

Monitors button presses and reports their raw event codes.
Useful for debugging and mapping button configurations.
"""

import sys
import os
import select

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def print_header(title):
    """Print a formatted header"""
    print()
    print("═" * 60)
    print(f"  {title}")
    print("═" * 60)


def find_mx_master_4_evdev():
    """Find MX Master 4 input device via evdev"""
    try:
        import evdev
    except ImportError:
        print("evdev not installed. Install with: pip install evdev")
        return None

    for path in evdev.list_devices():
        device = evdev.InputDevice(path)
        name = device.name.lower()

        if "mx master 4" in name or "b042" in name:
            return device

        # Also check for Bolt receiver mice
        if "logitech" in name and "mouse" in name:
            # Check capabilities for buttons
            caps = device.capabilities()
            if evdev.ecodes.EV_KEY in caps:
                keys = caps[evdev.ecodes.EV_KEY]
                if evdev.ecodes.BTN_LEFT in keys:
                    return device

    return None


def listen_evdev():
    """Listen for events via evdev"""
    try:
        import evdev
        from evdev import ecodes
    except ImportError:
        print("evdev not installed. Install with: pip install evdev")
        return False

    print_header("Button Event Listener (evdev)")

    print("\nSearching for MX Master 4...")
    device = find_mx_master_4_evdev()

    if not device:
        print("MX Master 4 not found via evdev!")
        print("\nAvailable input devices:")
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            print(f"  {path}: {dev.name}")
        return False

    print(f"Found: {device.name}")
    print(f"Path: {device.path}")

    # Get capabilities
    caps = device.capabilities(verbose=True)
    if (ecodes.EV_KEY, 'EV_KEY') in caps:
        buttons = caps[(ecodes.EV_KEY, 'EV_KEY')]
        print(f"\nDetected {len(buttons)} button(s)/key(s)")

    print("\n" + "-" * 60)
    print("Listening for button events... (Press Ctrl+C to stop)")
    print("-" * 60 + "\n")

    # Button name mapping
    button_names = {
        ecodes.BTN_LEFT: "Left Click",
        ecodes.BTN_RIGHT: "Right Click",
        ecodes.BTN_MIDDLE: "Middle Click",
        ecodes.BTN_SIDE: "Side (Back)",
        ecodes.BTN_EXTRA: "Extra (Forward)",
        ecodes.BTN_FORWARD: "Forward",
        ecodes.BTN_BACK: "Back",
        ecodes.BTN_TASK: "Task",
    }

    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY:
                keycode = event.code
                value = event.value

                state = "pressed" if value == 1 else "released" if value == 0 else "held"
                name = button_names.get(keycode, f"Button {keycode}")

                print(f"  {name:20s} {state:10s} (code: {keycode}, value: {value})")

            elif event.type == ecodes.EV_REL:
                # Scroll events
                if event.code == ecodes.REL_WHEEL:
                    direction = "up" if event.value > 0 else "down"
                    print(f"  {'Scroll':20s} {direction:10s} (delta: {event.value})")
                elif event.code == ecodes.REL_HWHEEL:
                    direction = "right" if event.value > 0 else "left"
                    print(f"  {'H-Scroll':20s} {direction:10s} (delta: {event.value})")
                elif event.code == ecodes.REL_WHEEL_HI_RES:
                    direction = "up" if event.value > 0 else "down"
                    print(f"  {'Scroll (Hi-Res)':20s} {direction:10s} (delta: {event.value})")

    except KeyboardInterrupt:
        print("\n\nStopped listening.")

    return True


def listen_hidraw():
    """Listen for raw HID events"""
    try:
        import hid
    except ImportError:
        print("hidapi not installed. Install with: pip install hidapi")
        return False

    from core.hidpp import find_mx_master_4

    print_header("Raw HID Listener")

    print("\nSearching for MX Master 4...")
    device_info = find_mx_master_4()

    if not device_info:
        print("MX Master 4 not found!")
        return False

    print(f"Found: {device_info.get('product_string', 'MX Master 4')}")

    try:
        device = hid.device()
        device.open_path(device_info["path"])
        device.set_nonblocking(True)

        print("\n" + "-" * 60)
        print("Listening for HID reports... (Press Ctrl+C to stop)")
        print("-" * 60 + "\n")

        while True:
            try:
                data = device.read(64, 100)
                if data:
                    # Format as hex
                    hex_str = " ".join(f"{b:02x}" for b in data)
                    print(f"  [{len(data):2d}] {hex_str}")

            except KeyboardInterrupt:
                break

        device.close()

    except Exception as e:
        print(f"Error: {e}")
        return False

    print("\nStopped listening.")
    return True


def main():
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║          MX4Control - Button Event Listener                ║")
    print("╚════════════════════════════════════════════════════════════╝")

    if len(sys.argv) > 1:
        if sys.argv[1] == "-r" or sys.argv[1] == "--raw":
            return 0 if listen_hidraw() else 1

    return 0 if listen_evdev() else 1


if __name__ == "__main__":
    sys.exit(main())
