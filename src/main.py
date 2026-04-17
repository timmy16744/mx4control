#!/usr/bin/env python3
"""
MX4Control - Logitech MX Master 4 Configuration for Linux

A gorgeous GTK4/Libadwaita application for configuring the
MX Master 4 mouse with full feature support including haptic
feedback, Actions Ring, and per-application profiles.

Can also be driven from the command line for use by external UIs
(waybar / AGS popup / shell scripts). In CLI mode the app opens
the hidraw node, performs a single operation, and exits — which
is safe to run concurrently with the full GUI because HID++ hidraw
access is non-exclusive.
"""

import sys
import json
import argparse
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


def _cli_main(args) -> int:
    """Handle --state / --set-* flags without launching the GUI."""
    # Suppress the noisy warning logger output on stderr
    import logging
    logging.basicConfig(level=logging.ERROR)

    from core.hidpp import find_mx_master_4, MXMaster4

    info = find_mx_master_4()
    if not info:
        print(json.dumps({"ok": False, "error": "no-device"}))
        return 2

    dev = MXMaster4(info["path"], device_index=info["device_index"])
    if not dev.open():
        print(json.dumps({"ok": False, "error": "open-failed"}))
        return 3

    try:
        if args.state:
            devinfo = dev.get_device_info()
            dpi = dev.get_dpi()
            ss_enabled, ss_threshold = dev.get_smartshift_status()
            payload = {
                "ok": True,
                "name": devinfo.name if devinfo else "MX Master 4",
                "firmware": devinfo.firmware_version if devinfo else None,
                "battery": devinfo.battery_level if devinfo else None,
                "charging": devinfo.battery_charging if devinfo else False,
                "connection": devinfo.connection_type if devinfo else None,
                "dpi": dpi,
                "smartshift": ss_enabled,
                "smartshift_threshold": ss_threshold,
            }
            print(json.dumps(payload))
            return 0

        if args.set_dpi is not None:
            ok = dev.set_dpi(args.set_dpi)
            print(json.dumps({"ok": ok, "dpi": args.set_dpi}))
            return 0 if ok else 4

        if args.set_smartshift is not None:
            enabled = args.set_smartshift.lower() in ("1", "on", "true", "yes")
            threshold = args.smartshift_threshold or 25
            ok = dev.set_smartshift(enabled, threshold)
            print(json.dumps({"ok": ok, "smartshift": enabled, "threshold": threshold}))
            return 0 if ok else 4

        if args.test_haptic is not None:
            ok = dev.trigger_haptic(args.test_haptic)
            print(json.dumps({"ok": ok, "pattern": args.test_haptic}))
            return 0 if ok else 4

        print(json.dumps({"ok": False, "error": "no-action"}))
        return 1
    finally:
        dev.close()


def main():
    """Application entry point."""
    parser = argparse.ArgumentParser(
        prog="mx4control",
        description="Logitech MX Master 4 configuration (GUI + CLI)",
    )
    parser.add_argument("--state", action="store_true",
                        help="Print current device state as JSON and exit")
    parser.add_argument("--set-dpi", type=int, metavar="N",
                        help="Set DPI (200-8000) and exit")
    parser.add_argument("--set-smartshift", metavar="on|off",
                        help="Enable / disable SmartShift and exit")
    parser.add_argument("--smartshift-threshold", type=int, metavar="N",
                        help="Threshold for --set-smartshift (1-255, default 25)")
    parser.add_argument("--test-haptic", type=int, metavar="PATTERN",
                        help="Trigger haptic pattern 0-14 and exit")
    # Unknown args get passed to GTK
    args, unknown = parser.parse_known_args()

    if args.state or args.set_dpi is not None or args.set_smartshift is not None or args.test_haptic is not None:
        return _cli_main(args)

    # GUI launch path
    from gi.repository import Gio
    from application import MX4ControlApplication

    app = MX4ControlApplication()
    return app.run([sys.argv[0]] + unknown)


if __name__ == "__main__":
    sys.exit(main())
