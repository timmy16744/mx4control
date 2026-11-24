"""mx4ctl — full CLI for MX4Control 1.0 (Logitech MX Master 4).

Talks to ``org.mx4control.System`` (device ops) on the system bus and
``org.mx4control.Agent`` (gesture/profile) on the session bus. Emits
compact JSON with ``--json`` for Waybar / AGS / scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..common.dbus import AgentClient, DaemonUnavailable, SystemClient


def _print_json(data: Any) -> None:
    print(json.dumps(data, separators=(",", ":")))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mx4ctl")
    parser.add_argument("--json", action="store_true", help="always emit JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state", help="print full live device & agent state")
    sub.add_parser("ping", help="check whether mx4-sysd and mx4-agent are alive")
    sub.add_parser("reload", help="reapply device config + reload agent profiles")
    sub.add_parser("buttons", help="list reprogrammable controls")
    sub.add_parser("hosts", help="list Easy-Switch host slots & names")
    sub.add_parser("probe", help="probe all 45 HID++ 2.0 features on the mouse")
    sub.add_parser("migrate", help="archive legacy v1 config.json/profiles.json")

    p_dpi = sub.add_parser("dpi", help="set pointer DPI (200–8000)")
    p_dpi.add_argument("value", type=int)

    p_mode = sub.add_parser("scroll-mode", help="set MagSpeed scroll mode")
    p_mode.add_argument("mode", choices=["smart", "ratchet", "free"])
    p_mode.add_argument("--threshold", type=int, default=15)
    p_mode.add_argument("--torque", type=int, default=75)

    p_ss = sub.add_parser("smartshift", help="enable/disable SmartShift")
    p_ss.add_argument("state", choices=["on", "off"])
    p_ss.add_argument("--threshold", type=int, default=15)
    p_ss.add_argument("--torque", type=int, default=None)

    p_tq = sub.add_parser("torque", help="set MagSpeed ratchet torque (1–100%%)")
    p_tq.add_argument("value", type=int)

    p_hir = sub.add_parser("hires", help="high-resolution vertical scrolling")
    p_hir.add_argument("state", choices=["on", "off"])
    p_hir.add_argument("--invert", action="store_true")

    p_hp = sub.add_parser("haptic-power", help="enable/disable haptic motor & strength (0x19B0)")
    p_hp.add_argument("state", choices=["on", "off"])
    p_hp.add_argument("--level", type=int, default=50)

    p_hap = sub.add_parser("haptic", help="play a haptic waveform (0–14)")
    p_hap.add_argument("pattern", type=int)

    p_force = sub.add_parser("force", help="get/set thumb-pad actuation force (0x19C0)")
    p_force.add_argument("value", nargs="?", default=None, help="raw force value or 'default'")

    p_host = sub.add_parser("host", help="switch Easy-Switch host slot (0-indexed)")
    p_host.add_argument("index", type=int)

    p_rhost = sub.add_parser("rename-host", help="rename an Easy-Switch host slot")
    p_rhost.add_argument("index", type=int)
    p_rhost.add_argument("name", type=str)

    p_name = sub.add_parser("friendly-name", help="set device friendly name (0x0007)")
    p_name.add_argument("name", type=str)

    p_tw = sub.add_parser("thumbwheel", help="configure thumb wheel mode (hd_scroll/native/actions) & 6x HD tuning")
    p_tw.add_argument("state", choices=["hd_scroll", "native", "actions", "on", "off"])
    p_tw.add_argument("--invert", action="store_true")
    p_tw.add_argument("--speed", type=float, default=1.0, help="HD horizontal speed multiplier (0.20–4.00)")
    p_tw.add_argument("--smooth", type=int, default=35, help="144Hz horizontal smooth inertia (0–100)")
    p_tw.add_argument("--accel", type=int, default=25, help="dynamic flick acceleration (0–100)")
    p_tw.add_argument("--no-hires", action="store_true", help="disable REL_HWHEEL_HI_RES sub-detent output")
    p_tw.add_argument("--haptic", action="store_true", help="virtual LRA haptic detents in HD scroll")
    p_tw.add_argument("--density", type=int, choices=[1, 2, 3, 6], default=6, help="HD haptic detent density (6=micro 120/rev, 1=notch 20/rev)")
    p_tw.add_argument("--pattern", type=int, default=1, help="haptic waveform id (0–14)")

    p_st = sub.add_parser("scroll-tuning", help="tune HD smooth scroll speed/smoothness/acceleration")
    p_st.add_argument("--speed", type=float, default=1.0, help="speed multiplier (0.20–4.00)")
    p_st.add_argument("--smooth", type=int, default=0, help="144Hz smooth scroll inertia (0–100)")
    p_st.add_argument("--accel", type=int, default=0, help="dynamic flick acceleration (0–100)")

    p_raw = sub.add_parser("raw", help="raw HID++ 2.0 feature call (RE/debug)")
    p_raw.add_argument("feature", type=lambda s: int(s, 0))
    p_raw.add_argument("function", type=lambda s: int(s, 0))
    p_raw.add_argument("args", nargs="*", type=lambda s: int(s, 0))
    p_raw.add_argument("--long", action="store_true")
    return parser


def _migrate() -> int:
    from ..config.paths import session_config_path
    base = session_config_path().parent
    moved = []
    for rel in ("config.json", "profiles/profiles.json", "profiles"):
        p = base / rel
        if p.exists():
            bak = p.with_suffix(p.suffix + ".bak") if p.is_file() else p.with_name("profiles.bak")
            try:
                p.rename(bak)
                moved.append(f"{p} -> {bak}")
            except OSError as e:
                print(f"could not archive {p}: {e}", file=sys.stderr)
    print("\n".join(moved) if moved else "nothing to migrate (no legacy files)")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    if args.cmd == "migrate":
        return _migrate()
    try:
        sysd = SystemClient()
    except Exception as e:
        return _fail(args, f"system bus error: {e}")

    try:
        return _dispatch(args, sysd)
    except DaemonUnavailable as e:
        return _fail(args, str(e))
    except Exception as e:
        return _fail(args, f"{args.cmd} failed: {e}")


def _dispatch(args, sysd: SystemClient) -> int:
    if args.cmd == "ping":
        ok = sysd.available()
        agent_ok = False
        try:
            agent_ok = AgentClient().available()
        except Exception:
            pass
        if args.json:
            _print_json({"ok": ok, "sysd": ok, "agent": agent_ok})
        else:
            print(f"mx4-sysd:  {'running' if ok else 'not running'}")
            print(f"mx4-agent: {'running' if agent_ok else 'not running'}")
        return 0 if ok else 1

    if args.cmd == "state":
        state = sysd.get_state()
        try:
            agent = AgentClient()
            active, cid = agent.gesture_status()
            if agent.available():
                state["gesture_active"] = active
                state["trigger_cid"] = cid
                prof = agent.get_active_profile()
                if prof.get("app_id"):
                    state["active_profile"] = prof["app_id"]
        except Exception:
            pass
        _print_json(state) if args.json else _print_state(state)
        return 0

    if args.cmd == "reload":
        ok = sysd.reload_config()
        agent_ok = False
        try:
            agent = AgentClient()
            if agent.available():
                agent_ok = agent.reload_profiles()
        except Exception:
            pass
        if args.json:
            _print_json({"ok": ok, "agent": agent_ok})
        return 0 if ok else 1

    if args.cmd == "buttons":
        btns = sysd.get_buttons()
        if args.json:
            _print_json(btns)
        else:
            for b in btns:
                print(
                    f"cid={b['cid']:#06x} task={b['task_id']:#06x} "
                    f"flags={b['flags']:#04x} "
                    f"{'divertable' if b['divertable'] else ''} "
                    f"{'remappable' if b['remappable'] else ''}"
                )
        return 0

    if args.cmd == "hosts":
        hosts = sysd.get_hosts()
        if args.json:
            _print_json(hosts)
        else:
            for h in hosts:
                cur = "*" if h.get("current") else " "
                status = h.get("name") or ("Paired" if h.get("paired") else "Unpaired")
                bus = h.get("bus_label", "") if h.get("paired") else ""
                print(f"{cur} Slot {int(h['index']) + 1}: {status:20s} {bus}")
        return 0

    if args.cmd == "probe":
        rows = sysd.probe_features()
        if args.json:
            _print_json(rows)
        else:
            for r in rows:
                res = "LOCKED" if r["locked"] else (r["response_hex"] or r["error"] or "—")
                print(f"#{r['index']:02d} {r['feature_hex']} {r['name']:28s} {res}")
        return 0

    if args.cmd == "dpi":
        ok = sysd.set_dpi(args.value)
        if args.json:
            _print_json({"ok": ok, "dpi": args.value})
        return 0 if ok else 1

    if args.cmd == "scroll-mode":
        ok = sysd.set_scroll_mode(args.mode, args.threshold, args.torque, True)
        if args.json:
            _print_json({"ok": ok, "mode": args.mode, "threshold": args.threshold, "torque": args.torque})
        return 0 if ok else 1

    if args.cmd == "smartshift":
        if args.torque is not None:
            mode = "smart" if args.state == "on" else "ratchet"
            ok = sysd.set_scroll_mode(mode, args.threshold, args.torque, True)
        else:
            ok = sysd.set_smartshift(args.state == "on", args.threshold)
        if args.json:
            _print_json({"ok": ok})
        return 0 if ok else 1

    if args.cmd == "torque":
        st = sysd.get_state()
        mode = str(st.get("wheel_mode", "ratchet"))
        thr = int(st.get("smartshift_threshold", 15))
        ok = sysd.set_scroll_mode(mode, thr, args.value, True)
        if args.json:
            _print_json({"ok": ok, "torque": args.value})
        return 0 if ok else 1

    if args.cmd == "hires":
        ok = sysd.set_hires(args.state == "on", args.invert)
        if args.json:
            _print_json({"ok": ok})
        return 0 if ok else 1

    if args.cmd == "scroll-tuning":
        ok = sysd.set_scroll_tuning(args.speed, args.smooth, args.accel, True)
        if args.json:
            _print_json({"ok": ok, "speed": args.speed, "smooth": args.smooth, "accel": args.accel})
        return 0 if ok else 1

    if args.cmd == "haptic-power":
        ok = sysd.set_haptic(args.state == "on", args.level, True)
        if args.json:
            _print_json({"ok": ok, "enabled": args.state == "on", "level": args.level})
        return 0 if ok else 1

    if args.cmd == "haptic":
        ok = sysd.trigger_haptic(args.pattern)
        if args.json:
            _print_json({"ok": ok})
        return 0 if ok else 1

    if args.cmd == "force":
        if args.value is None:
            info = sysd.get_force_button()
            if args.json:
                _print_json(info)
            elif info.get("supported"):
                print(
                    f"force: {info['value']} ({info['percent']}%) "
                    f"[min={info['min']} default={info['default']} max={info['max']}]"
                )
            else:
                print("force-sensing button not supported")
            return 0
        val = 0 if str(args.value).lower() == "default" else int(args.value)
        ok = sysd.set_force_threshold(val, True)
        if args.json:
            _print_json({"ok": ok, "value": val})
        return 0 if ok else 1

    if args.cmd == "host":
        ok = sysd.switch_host(args.index)
        if args.json:
            _print_json({"ok": ok})
        return 0 if ok else 1

    if args.cmd == "rename-host":
        ok = sysd.rename_host(args.index, args.name)
        if args.json:
            _print_json({"ok": ok})
        return 0 if ok else 1

    if args.cmd == "friendly-name":
        ok = sysd.set_friendly_name(args.name)
        if args.json:
            _print_json({"ok": ok})
        return 0 if ok else 1

    if args.cmd == "thumbwheel":
        mode_map = {"on": "actions", "off": "native"}
        mode = mode_map.get(args.state, args.state)
        ok = sysd.set_thumbwheel_tuning(
            mode,
            args.invert,
            args.speed,
            args.smooth,
            args.accel,
            not args.no_hires,
            args.haptic,
            True,
        )
        if ok:
            try:
                sysd.set_thumbwheel_haptics(args.density, args.pattern, True)
            except Exception:
                pass
        if args.json:
            _print_json({
                "ok": ok,
                "mode": mode,
                "invert": args.invert,
                "speed": args.speed,
                "smooth": args.smooth,
                "accel": args.accel,
                "haptic": args.haptic,
                "density": args.density,
                "pattern": args.pattern,
            })
        return 0 if ok else 1

    if args.cmd == "raw":
        resp = sysd.raw_call(args.feature, args.function, args.args, args.long)
        hexstr = resp.hex(" ")
        if args.json:
            _print_json({"response": hexstr})
        else:
            print(hexstr or "(no response)")
        return 0
    return 1


def _fail(args, msg: str) -> int:
    if args.json:
        _print_json({"ok": False, "error": msg})
    else:
        print(f"mx4ctl: {msg}", file=sys.stderr)
        print("start the daemon with: sudo systemctl start mx4-sysd", file=sys.stderr)
    return 2


def _print_state(state: dict) -> None:
    if not state.get("connected"):
        print("status:     disconnected (mouse asleep or daemon has no device)")
        return
    chg = " (charging)" if state.get("charging") else ""
    print(f"name:       {state.get('friendly_name') or state.get('name')}")
    print(f"firmware:   {state.get('firmware')}")
    print(f"battery:    {state.get('battery')}% ({state.get('battery_level_name', '')}){chg}")
    print(f"transport:  {state.get('connection')}")
    print(f"dpi:        {state.get('dpi')}")
    print(
        f"scroll:     {state.get('wheel_mode', 'smart')} "
        f"(threshold={state.get('smartshift_threshold')}, torque={state.get('ratchet_torque', 75)}%)"
    )
    print(
        f"hires:      {'on' if state.get('hires_enabled') else 'off'} "
        f"(invert={'on' if state.get('hires_invert') else 'off'})"
    )
    tw_mode = state.get("thumbwheel_mode") or ("actions" if state.get("thumbwheel_diverted") else "native")
    tw_extra = ""
    if tw_mode == "hd_scroll":
        tw_extra = (
            f", 6x HD speed={float(state.get('thumbwheel_speed', 1.0)):.2f}x "
            f"smooth={state.get('thumbwheel_smoothness', 35)}% "
            f"accel={state.get('thumbwheel_accel', 25)}%"
            f"{' +haptic' if state.get('thumbwheel_haptic_detent') else ''}"
        )
    print(
        f"thumbwheel: {tw_mode} "
        f"(invert={'on' if state.get('thumbwheel_invert') else 'off'}{tw_extra})"
    )
    print(
        f"haptic:     {'on' if state.get('haptic_enabled') else 'off'} "
        f"(level={state.get('haptic_level', 0)}%)"
    )
    if state.get("force_supported"):
        print(
            f"force pad:  {state.get('force_value')} "
            f"(range {state.get('force_min')}–{state.get('force_max')}, default {state.get('force_default')})"
        )
    if "current_host" in state:
        print(f"host:       slot {int(state.get('current_host', 0)) + 1} of {state.get('num_hosts')}")
    if state.get("gesture_active"):
        print("gestures:   active")
    if state.get("active_profile"):
        print(f"profile:    {state.get('active_profile')}")


if __name__ == "__main__":
    sys.exit(main())
