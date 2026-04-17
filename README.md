# MX4 Control

Linux/Wayland control suite for the **Logitech MX Master 4** mouse —
Actions Ring, haptic feedback, DPI, SmartShift, Easy-Switch hosts, and
thumb-wheel diversion. Built around a long-running daemon that owns
the HID++ connection, with a GTK4 settings GUI, a CLI, and first-class
hooks for Waybar / AGS popups.

## Why this exists

Logitech's own Logi Options+ doesn't ship for Linux, and Solaar — while
excellent for most things — doesn't implement the **Actions Ring**: the
radial menu you get when you hold the thumb button and flick.

This project contributes the Actions Ring plus the few MX Master 4
specifics that Solaar hasn't caught up on yet.

## Architecture

```
   ┌───────────────────────┐
   │ mx4d (daemon)         │   Owns /dev/hidraw3 exclusively.
   │ ─────────────────────│    Single HID++ reader, sw_id-routed
   │ HID++ dispatcher      │    responses, notification subscribers.
   │ Gesture engine        │    Evdev grab for cursor freeze,
   │ Actions Ring overlay  │    layer-shell overlay at cursor.
   │ Hyprland watcher      │    Live focused-window events,
   │ IPC: unix socket      │    no subprocess polling.
   └─────────┬─────────────┘
             │  JSON-RPC
   ┌─────────┴───────────────────────────┐
   │                                     │
 ┌──▼──────────┐    ┌───────────────┐  ┌─▼───────────────┐
 │ mx4ctl      │    │ mx4-settings  │  │ Waybar / AGS    │
 │ CLI client  │    │ GTK4 GUI      │  │ popups          │
 └─────────────┘    └───────────────┘  └─────────────────┘
```

The daemon is the only process that opens `/dev/hidraw*` — so there's
never any fd contention, no racy notification drops, and multiple
clients can query state simultaneously.

## Installation

```bash
sudo ./install.sh
systemctl --user daemon-reload
systemctl --user enable --now mx4d.service
mx4ctl state
```

## Usage

```bash
mx4ctl state                     # JSON state (for scripting)
mx4ctl dpi 1600                  # set pointer DPI
mx4ctl smartshift on             # enable SmartShift
mx4ctl haptic 2                  # play haptic pattern 2
mx4ctl host 1                    # switch Easy-Switch host
mx4ctl thumbwheel on             # divert thumb wheel for custom actions
mx4-settings                     # open the GUI
```

## Reverse-engineering notes

Captured from firmware 4.5.0000 against a live MX Master 4 (Bolt):

* **`MX_SMART_ACTIONS (0x9401)` is firmware-locked.** Every function
  returns HID++ error 0x05 (Logitech internal). Cannot be unlocked via
  `ENABLE_HIDDEN_FEATURES` — that's a real cryptographic gate. Client-
  side simulation is the only path.
* **`GESTURE_2 (0x19B0)` is enumerated but all 16 gesture slots are
  disabled.** Can't offload gesture detection to firmware.
* **Haptic `0x0B4E` is a hidden / direct-address feature** — not in
  the enumerated feature list, but the device responds to writes with
  a magic 2-byte address. Short-message format:
  `10 DEV 0B 4E PATTERN 00 00`.
* **`THUMBWHEEL (0x2150)` can be diverted** — native res 20, diverted
  res 120, capabilities flag 0x03 (supports diversion + hi-res).
* **`REPROG_CONTROLS_V4` getCidReporting** returns
  `[cid(2), flags1, remap(2), flags2]` — the remap CID is at bytes
  3–4, not 4–5 as the v1 implementation had it.

The full probe (including every feature + response byte) is committed
at `tests/fixtures/mx4_master4_4.5.0000.json` and drives the protocol
regression tests.

## Development

```bash
pytest              # 21 tests (protocol, gesture math, config)
ruff check src/     # lint
```

## License

MIT.
