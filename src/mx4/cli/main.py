"""mx4ctl — control / query the MX Master 4 via the mx4d daemon.

Emits JSON for state queries (for use by Waybar / AGS popups) and
human-friendly output for interactive use. Never opens the hidraw node
directly — that's exclusively the daemon's job so there's no contention.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..common.ipc import DaemonClient


def _print_json(data: Any) -> None:
    print(json.dumps(data, separators=(",", ":")))


def main() -> int:
    parser = argparse.ArgumentParser(prog="mx4ctl")
    parser.add_argument("--json", action="store_true", help="always emit JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state", help="print current device state")
    sub.add_parser("ping", help="check whether the daemon is alive")
    sub.add_parser("reload", help="reload config.toml without restart")

    p_dpi = sub.add_parser("dpi", help="set DPI (200–8000)")
    p_dpi.add_argument("value", type=int)

    p_ss = sub.add_parser("smartshift", help="enable/disable SmartShift")
    p_ss.add_argument("state", choices=["on", "off"])
    p_ss.add_argument("--threshold", type=int, default=15)

    p_hir = sub.add_parser("hires", help="high-resolution scrolling")
    p_hir.add_argument("state", choices=["on", "off"])
    p_hir.add_argument("--invert", action="store_true")

    p_hap = sub.add_parser("haptic", help="play a haptic pattern 0–14")
    p_hap.add_argument("pattern", type=int)

    p_host = sub.add_parser("host", help="switch the mouse to another paired host")
    p_host.add_argument("index", type=int, help="0-indexed slot")

    p_tw = sub.add_parser("thumbwheel", help="divert thumb wheel (custom actions)")
    p_tw.add_argument("state", choices=["on", "off"])
    p_tw.add_argument("--invert", action="store_true")

    args = parser.parse_args()
    client = DaemonClient()

    try:
        if args.cmd == "state":
            state = client.state()
            if args.json:
                _print_json(state)
            else:
                _print_state(state)
            return 0

        if args.cmd == "ping":
            ok = client.is_running()
            if args.json:
                _print_json({"ok": ok})
            else:
                print("mx4d is " + ("running" if ok else "not running"))
            return 0 if ok else 1

        if args.cmd == "reload":
            ok = client.reload()
            if args.json:
                _print_json({"ok": ok})
            return 0 if ok else 1

        if args.cmd == "dpi":
            ok = client.set_dpi(args.value)
            if args.json:
                _print_json({"ok": ok, "dpi": args.value})
            return 0 if ok else 1

        if args.cmd == "smartshift":
            ok = client.set_smartshift(args.state == "on", args.threshold)
            if args.json:
                _print_json({"ok": ok})
            return 0 if ok else 1

        if args.cmd == "hires":
            r = client.call("set_hires",
                            enabled=args.state == "on",
                            invert=args.invert)
            if args.json:
                _print_json(r)
            return 0 if r.get("ok") else 1

        if args.cmd == "haptic":
            ok = client.trigger_haptic(args.pattern)
            if args.json:
                _print_json({"ok": ok})
            return 0 if ok else 1

        if args.cmd == "host":
            ok = client.switch_host(args.index)
            if args.json:
                _print_json({"ok": ok})
            return 0 if ok else 1

        if args.cmd == "thumbwheel":
            r = client.call("set_thumbwheel_diverted",
                            diverted=args.state == "on",
                            invert=args.invert)
            if args.json:
                _print_json(r)
            return 0 if r.get("ok") else 1

    except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
        if args.json:
            _print_json({"ok": False, "error": f"daemon-unreachable: {e}"})
        else:
            print(f"mx4d daemon not reachable: {e}", file=sys.stderr)
            print("start it with: systemctl --user start mx4d", file=sys.stderr)
        return 2

    return 1


def _print_state(state: dict) -> None:
    if not state.get("connected"):
        print("status: disconnected")
        return
    chg = " (charging)" if state.get("charging") else ""
    print(f"name:     {state.get('friendly_name') or state.get('name')}")
    print(f"firmware: {state.get('firmware')}")
    print(f"battery:  {state.get('battery')}%{chg}")
    print(f"conn:     {state.get('connection')}")
    print(f"dpi:      {state.get('dpi')}")
    ss = state.get("smartshift")
    thr = state.get("smartshift_threshold")
    print(f"smartsh:  {'on' if ss else 'off'} (threshold={thr})")
    if state.get("gesture_active"):
        print("gestures: on")
    if hosts := state.get("hosts"):
        print(f"hosts:    current={hosts['current_host']} paired={[h['index'] for h in hosts['hosts'] if h['paired']]}")


if __name__ == "__main__":
    sys.exit(main())
