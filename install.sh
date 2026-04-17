#!/bin/bash
# MX4Control Installation Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="mx4control"

echo "=== MX4Control Installer ==="
echo ""

# Check if running as root for system-wide install
if [ "$EUID" -eq 0 ]; then
    echo "Installing system-wide..."
    INSTALL_DIR="/opt/mx4control"
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    UDEV_DIR="/etc/udev/rules.d"
else
    echo "Installing for current user..."
    INSTALL_DIR="$HOME/.local/share/mx4control"
    BIN_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    UDEV_DIR=""

    echo ""
    echo "NOTE: udev rules require root. Run with sudo for full installation:"
    echo "  sudo $0"
    echo ""
fi

# Create directories
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
mkdir -p "$DESKTOP_DIR"

# Copy application files
echo "Copying application files..."
cp -r "$SCRIPT_DIR/src" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/mx4control.sh" "$INSTALL_DIR/"

# Create launcher script
echo "Creating launcher..."
cat > "$BIN_DIR/mx4control" << EOF
#!/bin/bash
cd "$INSTALL_DIR"
exec env LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so /usr/bin/python3 -u src/main.py "\$@"
EOF
chmod +x "$BIN_DIR/mx4control"

# Install desktop file
echo "Installing desktop entry..."
cat > "$DESKTOP_DIR/io.github.mx4control.desktop" << EOF
[Desktop Entry]
Name=MX4 Control
Comment=Logitech MX Master 4 gesture control
Exec=$BIN_DIR/mx4control
Icon=input-mouse
Terminal=false
Type=Application
Categories=Settings;HardwareSettings;
Keywords=logitech;mouse;gesture;mx;master;
StartupNotify=false
EOF

# Install udev rules (requires root)
if [ -n "$UDEV_DIR" ]; then
    echo "Installing udev rules..."
    cp "$SCRIPT_DIR/42-mx4control.rules" "$UDEV_DIR/"
    udevadm control --reload-rules
    udevadm trigger
    echo "udev rules installed and reloaded"
fi

# Add user to input group if not already
if ! groups | grep -q '\binput\b'; then
    if [ "$EUID" -eq 0 ]; then
        ACTUAL_USER="${SUDO_USER:-$USER}"
        usermod -aG input "$ACTUAL_USER"
        echo "Added $ACTUAL_USER to 'input' group (re-login required)"
    else
        echo ""
        echo "WARNING: You're not in the 'input' group. Run:"
        echo "  sudo usermod -aG input $USER"
        echo "Then log out and back in."
    fi
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Run with: mx4control"
echo ""
if [ "$EUID" -ne 0 ]; then
    echo "For udev rules (required for evdev access), run:"
    echo "  sudo cp $SCRIPT_DIR/42-mx4control.rules /etc/udev/rules.d/"
    echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
fi
