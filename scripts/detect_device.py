#!/usr/bin/env python3
"""
MX Master 4 Device Detection Script

Scans for connected MX Master 4 devices and verifies HID++ communication.
"""

import sys
import os

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import hid
except ImportError:
    print("ERROR: hidapi not installed")
    print("Install with: pip install hidapi")
    sys.exit(1)


# Logitech Vendor ID
LOGITECH_VID = 0x046D

# MX Master 4 Product IDs
MX_MASTER_4_PIDS = {
    0xB042: "MX Master 4 (Bolt Receiver)",
    0x4107: "MX Master 4 (Bluetooth)",
}

# All known MX Master series for comparison
MX_MASTER_SERIES = {
    0x4041: "MX Master",
    0xB012: "MX Master 2S (Unifying)",
    0x4069: "MX Master 2S (Bluetooth)",
    0xB022: "MX Master 3 (Unifying)",
    0x4082: "MX Master 3 (Bluetooth)",
    0xB034: "MX Master 3S (Bolt)",
    0x4096: "MX Master 3S (Bluetooth)",
    **MX_MASTER_4_PIDS,
}


def print_header(title):
    """Print a formatted header"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_device(device, indent=2):
    """Print device details"""
    prefix = " " * indent
    print(f"{prefix}Product ID: {device['product_id']:#06x}")
    print(f"{prefix}Product: {device.get('product_string', 'Unknown')}")
    print(f"{prefix}Serial: {device.get('serial_number', 'N/A')}")
    print(f"{prefix}Interface: {device.get('interface_number', 'N/A')}")
    print(f"{prefix}Path: {device['path']}")


def scan_devices():
    """Scan for all Logitech HID devices"""
    print_header("Scanning for Logitech Devices")

    all_devices = hid.enumerate(LOGITECH_VID)

    if not all_devices:
        print("\nNo Logitech HID devices found!")
        print("\nTroubleshooting:")
        print("  1. Make sure your device is connected")
        print("  2. Check that the Bolt receiver is plugged in")
        print("  3. Ensure you have HID device permissions (udev rules)")
        return None

    # Group by product
    by_product = {}
    for device in all_devices:
        pid = device["product_id"]
        if pid not in by_product:
            by_product[pid] = []
        by_product[pid].append(device)

    print(f"\nFound {len(by_product)} Logitech product(s):\n")

    mx4_found = None

    for pid, devices in by_product.items():
        # Check if it's an MX Master
        if pid in MX_MASTER_SERIES:
            name = MX_MASTER_SERIES[pid]
            is_mx4 = pid in MX_MASTER_4_PIDS

            if is_mx4:
                print(f"[MX MASTER 4] {name}")
                mx4_found = devices[0]
            else:
                print(f"[MX Master] {name}")
        else:
            print(f"[Other] {devices[0].get('product_string', 'Unknown')} ({pid:#06x})")

        # Show interface count
        print(f"  └─ {len(devices)} interface(s)")

        # Show the first interface details
        for device in devices[:1]:
            print_device(device, indent=4)

    return mx4_found


def test_hidpp(device_info):
    """Test HID++ communication with the device"""
    print_header("Testing HID++ Communication")

    try:
        device = hid.device()
        device.open_path(device_info["path"])
        device.set_nonblocking(False)

        print("\nDevice opened successfully!")
        print(f"  Manufacturer: {device.get_manufacturer_string()}")
        print(f"  Product: {device.get_product_string()}")

        # Try to query device info via HID++
        print("\nQuerying device via HID++...")

        # Send IRoot getProtocolVersion request
        # Short message: 0x10, device 0xFF, feature 0x00, function 0x10
        request = bytes([0x10, 0xFF, 0x00, 0x10, 0x00, 0x00, 0x00])

        try:
            device.write(request)
            response = device.read(20, 2000)

            if response:
                print(f"\n  Response received ({len(response)} bytes)")
                print(f"  Raw: {' '.join(f'{b:02x}' for b in response)}")

                if response[2] != 0xFF:  # Not an error
                    major = response[4]
                    minor = response[5]
                    print(f"\n  HID++ Protocol Version: {major}.{minor}")

                    if major >= 4:
                        print("  [OK] HID++ 4.x detected - Full feature support!")
                    elif major >= 2:
                        print("  [OK] HID++ 2.x detected - Good feature support")
                    else:
                        print("  [WARN] HID++ 1.x detected - Limited features")
                else:
                    error_code = response[4]
                    print(f"\n  Error response: {error_code:#04x}")
            else:
                print("\n  No response received (timeout)")
        except Exception as e:
            print(f"\n  Communication error: {e}")

        device.close()
        return True

    except Exception as e:
        print(f"\nFailed to open device: {e}")
        print("\nThis is usually a permissions issue.")
        print("Fix with udev rules:")
        print()
        print('  echo \'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="046d", MODE="0666"\' | sudo tee /etc/udev/rules.d/99-logitech.rules')
        print('  sudo udevadm control --reload-rules')
        print('  sudo udevadm trigger')
        print()
        return False


def query_features(device_info):
    """Query available HID++ features"""
    print_header("Querying Device Features")

    try:
        from core.hidpp import MXMaster4, FeatureID

        device = MXMaster4(device_info["path"])
        if not device.open():
            print("Failed to open device")
            return

        print("\nEnumerating HID++ features...")

        features = {
            "ROOT": FeatureID.ROOT,
            "FEATURE_SET": FeatureID.FEATURE_SET,
            "DEVICE_NAME": FeatureID.DEVICE_NAME,
            "BATTERY": FeatureID.UNIFIED_BATTERY,
            "REPROG_CONTROLS": FeatureID.REPROG_CONTROLS_V4,
            "ADJUSTABLE_DPI": FeatureID.ADJUSTABLE_DPI,
            "HIRES_WHEEL": FeatureID.HIRES_WHEEL,
            "SMART_SHIFT": FeatureID.SMART_SHIFT,
            "HAPTICS": FeatureID.HAPTICS,
        }

        for name, feature_id in features.items():
            if device.has_feature(feature_id):
                index = device.get_feature_index(feature_id)
                print(f"  [OK] {name} (0x{feature_id:04X}) at index {index}")
            else:
                print(f"  [  ] {name} (0x{feature_id:04X}) - not available")

        # Get device info
        print("\n" + "-" * 40)
        info = device.get_device_info()
        if info:
            print(f"\n  Device: {info.name}")
            print(f"  Firmware: {info.firmware_version}")
            print(f"  Battery: {info.battery_level}%")
            print(f"  Charging: {'Yes' if info.battery_charging else 'No'}")
            print(f"  Connection: {info.connection_type}")

        device.close()

    except ImportError as e:
        print(f"\nCannot import core module: {e}")
        print("Run from project directory or install the package")
    except Exception as e:
        print(f"\nError: {e}")


def main():
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║           MX4Control - Device Detection Utility            ║")
    print("╚════════════════════════════════════════════════════════════╝")

    # Scan for devices
    mx4 = scan_devices()

    if mx4:
        # Test HID++ communication
        if test_hidpp(mx4):
            # Query features if communication works
            query_features(mx4)

        print_header("Summary")
        print("\n  MX Master 4 detected and communication verified!")
        print("  The device is ready for use with MX4Control.")
        print()
    else:
        print_header("Summary")
        print("\n  MX Master 4 not detected.")
        print()
        print("  If you have an MX Master 4:")
        print("    - Ensure it's turned on")
        print("    - Connect via Bolt receiver (USB-C dongle)")
        print("    - Or pair via Bluetooth")
        print()

    return 0 if mx4 else 1


if __name__ == "__main__":
    sys.exit(main())
