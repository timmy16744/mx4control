#!/usr/bin/env python3
"""
MX Master 4 Haptic Feedback Test Script

Tests all haptic patterns and intensity levels.
"""

import sys
import os
import time

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def print_header(title):
    """Print a formatted header"""
    print()
    print("═" * 60)
    print(f"  {title}")
    print("═" * 60)


def test_haptics():
    """Test haptic feedback patterns"""
    try:
        from core.hidpp import MXMaster4, HapticPattern, FeatureID, find_mx_master_4
    except ImportError as e:
        print(f"Cannot import core module: {e}")
        print("Run from project directory or install the package")
        return False

    print_header("MX4Control - Haptic Feedback Test")

    # Find device
    print("\nSearching for MX Master 4...")
    device_info = find_mx_master_4()

    if not device_info:
        print("ERROR: MX Master 4 not found!")
        print("Make sure your device is connected and turned on.")
        return False

    print(f"Found: {device_info.get('product_string', 'MX Master 4')}")

    # Connect
    device = MXMaster4(device_info.get("path"))
    if not device.open():
        print("ERROR: Failed to open device")
        return False

    # Check for haptics feature
    if not device.has_feature(FeatureID.HAPTICS):
        print("\nWARNING: Haptics feature not detected!")
        print("This could mean:")
        print("  - The device doesn't support haptics (unlikely for MX4)")
        print("  - The feature index is different than expected")
        print("  - There's a communication issue")
        print("\nAttempting to trigger haptics anyway...")

    # Get current intensity
    current_intensity = device.get_haptic_intensity()
    print(f"\nCurrent haptic intensity: {current_intensity}")

    # Define all patterns
    patterns = [
        (HapticPattern.SOFT_BUMP, "Soft Bump", "Gentle nudge"),
        (HapticPattern.LIGHT_CLICK, "Light Click", "Subtle tap"),
        (HapticPattern.MEDIUM_CLICK, "Medium Click", "Standard feel"),
        (HapticPattern.STRONG_CLICK, "Strong Click", "Firm response"),
        (HapticPattern.SOFT_PULSE, "Soft Pulse", "Light vibration"),
        (HapticPattern.MEDIUM_PULSE, "Medium Pulse", "Moderate buzz"),
        (HapticPattern.STRONG_PULSE, "Strong Pulse", "Strong vibration"),
        (HapticPattern.RAMP_UP, "Ramp Up", "Building intensity"),
        (HapticPattern.RAMP_DOWN, "Ramp Down", "Fading intensity"),
        (HapticPattern.DOUBLE_TAP, "Double Tap", "Two quick taps"),
        (HapticPattern.TRIPLE_TAP, "Triple Tap", "Three quick taps"),
        (HapticPattern.ALERT, "Alert", "Attention grab"),
        (HapticPattern.SUCCESS, "Success", "Confirmation"),
        (HapticPattern.ERROR, "Error", "Warning signal"),
    ]

    print_header("Pattern Test")
    print("\nTesting all 14 haptic patterns...")
    print("You should feel a vibration for each pattern.\n")

    for i, (pattern, name, desc) in enumerate(patterns):
        print(f"  [{i+1:2d}/14] {name:15s} - {desc}")
        sys.stdout.flush()

        success = device.trigger_haptic(pattern)

        if success:
            print(" ✓")
        else:
            print(" ✗ (failed)")

        time.sleep(0.5)  # Pause between patterns

    print_header("Intensity Test")
    print("\nTesting intensity levels with Medium Click...")

    intensity_names = ["Subtle", "Low", "Medium", "High"]

    for level in range(4):
        print(f"\n  Intensity {level} ({intensity_names[level]})...")
        device.set_haptic_intensity(level)
        time.sleep(0.2)
        device.trigger_haptic(HapticPattern.MEDIUM_CLICK)
        time.sleep(0.8)

    # Restore original intensity
    device.set_haptic_intensity(current_intensity)
    print(f"\n  Restored intensity to {current_intensity}")

    print_header("Quick Pattern Demo")
    print("\nPlaying a short haptic sequence...")

    sequence = [
        (HapticPattern.LIGHT_CLICK, 0.1),
        (HapticPattern.MEDIUM_CLICK, 0.1),
        (HapticPattern.STRONG_CLICK, 0.2),
        (HapticPattern.DOUBLE_TAP, 0.3),
        (HapticPattern.SUCCESS, 0.5),
    ]

    for pattern, delay in sequence:
        device.trigger_haptic(pattern)
        time.sleep(delay)

    device.close()

    print_header("Test Complete")
    print("\n  All haptic tests completed!")
    print("  If you felt the vibrations, haptics are working correctly.")
    print()

    return True


def interactive_test():
    """Run an interactive haptic testing session"""
    try:
        from core.hidpp import MXMaster4, HapticPattern, find_mx_master_4
    except ImportError as e:
        print(f"Cannot import core module: {e}")
        return False

    print_header("Interactive Haptic Test")

    device_info = find_mx_master_4()
    if not device_info:
        print("ERROR: MX Master 4 not found!")
        return False

    device = MXMaster4(device_info.get("path"))
    if not device.open():
        print("ERROR: Failed to open device")
        return False

    patterns = list(HapticPattern)

    print("\nCommands:")
    print("  0-13 : Trigger specific pattern")
    print("  i0-3 : Set intensity (0=subtle, 3=high)")
    print("  a    : Test all patterns")
    print("  q    : Quit")
    print()

    while True:
        try:
            cmd = input("haptic> ").strip().lower()

            if cmd == 'q':
                break
            elif cmd == 'a':
                for p in patterns:
                    device.trigger_haptic(p)
                    time.sleep(0.4)
            elif cmd.startswith('i') and len(cmd) == 2:
                level = int(cmd[1])
                if 0 <= level <= 3:
                    device.set_haptic_intensity(level)
                    print(f"Set intensity to {level}")
            elif cmd.isdigit():
                idx = int(cmd)
                if 0 <= idx < len(patterns):
                    device.trigger_haptic(patterns[idx])
                    print(f"Triggered: {patterns[idx].name}")
        except (ValueError, IndexError):
            print("Invalid command")
        except KeyboardInterrupt:
            break

    device.close()
    return True


def main():
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║          MX4Control - Haptic Feedback Test Utility         ║")
    print("╚════════════════════════════════════════════════════════════╝")

    if len(sys.argv) > 1 and sys.argv[1] == "-i":
        return 0 if interactive_test() else 1
    else:
        return 0 if test_haptics() else 1


if __name__ == "__main__":
    sys.exit(main())
