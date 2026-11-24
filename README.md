<div align="center">

# MX4 STUDIO

### Precision Linux & Wayland Control for the Logitech MX Master 4

**Real-time 3D WebGL2 hardware studio · Native HID++ 2.0 daemon · 60 FPS Wayland Actions Ring · 15-waveform LRA haptics**

[![Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Wayland-3ce0e8?style=flat-square&labelColor=0b0e14)](https://github.com/timmy16744/mx4control)
[![HID++ 2.0](https://img.shields.io/badge/Protocol-HID%2B%2B%202.0-e8a864?style=flat-square&labelColor=0b0e14)](https://github.com/timmy16744/mx4control)
[![License: MIT](https://img.shields.io/badge/License-MIT-a0aec0?style=flat-square&labelColor=0b0e14)](https://github.com/timmy16744/mx4control)
[![Donate](https://img.shields.io/badge/Donate-Buy%20my%201%20year%20old%20son%20nappies%20to%20say%20thanks-ff6b81?style=flat-square&labelColor=0b0e14&logo=paypal&logoColor=white)](https://www.paypal.com/qrcodes/p2pqrc/T4X8KXBNDDALL)

</div>

---

**MX4 Studio (`mx4control`)** unlocks every hardware capability of the **Logitech MX Master 4** natively on Linux — no Wine, no Logi Options+, no compromise. Built around a split systemd/D-Bus architecture (`mx4-sysd` + `mx4-agent`) and a hardware-accelerated 3D WebGL2 Studio interface, every adjustment writes directly to the mouse over HID++ 2.0 and reflects in real time.

## Flagship Capabilities

| Subsystem | HID++ 2.0 | What It Unlocks |
|---|---|---|
| **Darkfield 8000 DPI & Real-Time 3D Telemetry** | `0x2201` | 200–8000 DPI in 50-DPI hardware steps, custom DPI cycle stages, live 60 Hz physical glide/click/wheel mirroring on an interactive 3D MX Master 4 CAD model + 625-cube optical pulse floor. |
| **MagSpeed Electromagnetic Scroll & HD Smooth Engine** | `0x2111` · `0x2121` | SmartShift (threshold 1–50), Ratchet, Free-Spin, **hardware tunable ratchet torque (1–100%)**, interactive S-curve feel tuning, and 144 Hz hi-res smooth scrolling. |
| **LRA Haptic Motor & Force-Sensing Thumb Pad** | `0x19B0` · `0x19C0` | Master motor switch, 1–100% strength, all **15 built-in hardware waveforms** with a live oscilloscope, tunable thumb-pad actuation force (`4156–6909`), and desktop notification haptics. |
| **60 FPS Wayland Actions Ring** | `0x1B04` + `gtk4-layer-shell` | **6 curated visual themes** (*Studio Copper, Darkfield Cyber, Monochrome Pro, Amber Forge, Nordic Emerald, Ultraviolet Pulse*), **8 one-click workflow presets** (including *Hyprland WM*, *PipeWire Media*, *Code/IDE*, *MX4 Hardware Deck*), live analog magnetic compass tracking, per-app auto-switching, and Compact/Standard/Large sizing. |
| **Direct Click-to-Zoom Control Inspector** | `0x1B04` · `0x2150` | Click any physical button, clicker, scroll wheel, thumb wheel, or thumb pad on the 3D mouse to zoom directly into its dedicated settings, record keystrokes, bind hardware actions, or assign per-app overrides. |
| **Easy-Switch Hosts & Hardware Lab** | `0x1814` · `0x1815` · `0x0007` | Live Bolt/BLE slot telemetry, one-click host switching, firmware host/device renaming, instant wake re-sync, and a live 45-feature HID++ 2.0 feature probe. |

## Architecture

```text
mx4-sysd (root, systemd) ── HID++ 2.0 ──► Logitech MX Master 4 (Bolt / BLE)
   │  System D-Bus: org.mx4control.System  (/etc/mx4control/device.toml)
   ├── mx4-settings   Native QtWebEngine + WebGL2 3D MX4 Studio
   ├── mx4ctl         Scriptable CLI & JSON telemetry (Waybar / AGS / scripts)
   └── mx4-agent      User session daemon (org.mx4control.Agent)
                        ├── 60 FPS Wayland Actions Ring (gtk4-layer-shell + Cairo)
                        ├── Zero-latency Hyprland / Sway / X11 focus watcher
                        ├── Diverted button & thumb-wheel action dispatchers
                        └── Desktop notification haptic watcher
```

## Prerequisites

Install the system packages for your distribution (Python 3.12+, Qt6 WebEngine / PySide6, GTK4 Layer Shell, HID++ & evdev bindings):

- **Arch Linux:** `sudo pacman -S python-pyside6 qt6-webengine gtk4-layer-shell python-gobject python-cairo python-hidapi python-evdev python-pyudev python-tomlkit wtype`
- **Fedora:** `sudo dnf install python3-pyside6 qt6-qtwebengine gtk4-layer-shell python3-gobject python3-cairo python3-hidapi python3-evdev python3-pyudev python3-tomlkit wtype`
- **Ubuntu / Debian:** `sudo apt install python3-pyside6.qtwebenginewidgets libgtk4-layer-shell0 python3-gi python3-cairo python3-hid python3-evdev python3-pyudev python3-tomlkit wtype`

## Quick Install

```bash
git clone https://github.com/timmy16744/mx4control.git
cd mx4control
sudo ./install.sh
sudo systemctl enable --now mx4-sysd.service
systemctl --user enable --now mx4-agent.service
```

Launch **MX4 Studio** from your application launcher or run:

```bash
mx4-settings
```

## CLI Quick Reference (`mx4ctl`)

```bash
mx4ctl state                                    # live hardware & agent snapshot
mx4ctl dpi 1600                                 # set sensor DPI (200–8000)
mx4ctl scroll-mode smart --threshold 20 --torque 75
mx4ctl scroll-mode free                         # frictionless MagSpeed free-spin
mx4ctl haptic-power on --level 75               # enable LRA motor (0x19B0)
mx4ctl haptic 2                                 # fire hardware waveform 0–14
mx4ctl force default                            # reset thumb-pad press force
mx4ctl hosts                                    # list Easy-Switch slots
mx4ctl host 1                                   # switch active host slot
mx4ctl probe                                    # probe all 45 HID++ 2.0 features
```

## Development & Tests

```bash
PYTHONPATH=src pytest -q
ruff check src/ tests/
```

## Support

If MX4 Studio saved you time or unlocked your mouse on Linux, you can **[buy my 1 year old son nappies to say thanks](https://www.paypal.com/qrcodes/p2pqrc/T4X8KXBNDDALL)**.

## License

MIT — see [LICENSE](LICENSE).
