# MX4 Control

Gesture control application for the Logitech MX Master 4 mouse on Linux/Wayland.

## Features

- **Gesture Ring**: Hold the gesture button and move in any direction to trigger actions
- **Per-Application Profiles**: Different actions for different apps (browser, editor, terminal, etc.)
- **8-Segment Action Ring**: Visual overlay showing available actions
- **Wayland Native**: Uses wtype for keystroke injection, gtk4-layer-shell for overlays

## Requirements

- Linux with Wayland (Hyprland, Sway, etc.)
- Python 3.10+
- GTK4 with libadwaita
- gtk4-layer-shell
- Logitech MX Master 4 mouse

### Dependencies (Arch Linux)

```bash
sudo pacman -S python gtk4 libadwaita python-gobject wtype
yay -S gtk4-layer-shell  # or paru
```

### Dependencies (Ubuntu/Debian)

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 libadwaita-1-0 gir1.2-adw-1 wtype
# gtk4-layer-shell may need to be built from source
```

### Python Dependencies

```bash
pip install evdev
```

## Installation

```bash
git clone https://github.com/yourusername/mx4control.git
cd mx4control
chmod +x install.sh
sudo ./install.sh
```

This will:
- Install the application to `/opt/mx4control`
- Create a launcher at `/usr/local/bin/mx4control`
- Install udev rules for device access
- Add a desktop entry

## Manual Run (Development)

```bash
cd mx4control
LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so python -u src/main.py
```

## Usage

1. Launch `mx4control` from your application menu or terminal
2. Press and hold the gesture button on your MX Master 4
3. Move the mouse in a direction to highlight an action
4. Release to execute the action, or return to center to cancel

## Configuration

Profiles and settings are stored in `~/.config/mx4control/`

### Default Actions

| Direction | Action |
|-----------|--------|
| Up | Undo (Ctrl+Z) |
| Down | Redo (Ctrl+Y) |
| Left | Paste (Ctrl+V) |
| Right | Copy (Ctrl+C) |
| Up-Left | Select All (Ctrl+A) |
| Up-Right | Save (Ctrl+S) |
| Down-Left | Cut (Ctrl+X) |
| Down-Right | Find (Ctrl+F) |

### Per-App Profiles

The app automatically detects the focused application and can apply different action sets. Built-in templates exist for:
- Browsers (tabs, navigation)
- Editors (code actions)
- Terminals (pane management)
- Media players (playback control)
- Graphics apps (layer/tool shortcuts)

## Troubleshooting

### "No evdev mouse device found"

Ensure you're in the `input` group:
```bash
sudo usermod -aG input $USER
# Log out and back in
```

### Overlay not showing / layer-shell warnings

Make sure to run with LD_PRELOAD:
```bash
LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so mx4control
```

### Gesture button deselects text

This is a known limitation when HID++ diversion isn't working. The app grabs the device on button press to minimize this, but the initial press may still affect the OS.

## License

MIT License
