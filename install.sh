#!/bin/bash
# Install mx4control — daemon + CLI + settings GUI
#
# Run with sudo for system-wide installation including udev rules,
# without sudo for per-user installation under ~/.local.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -eq 0 ]]; then
    PREFIX="/usr/local"
    SYSTEM_INSTALL=1
    echo "=== Installing system-wide to $PREFIX ==="
else
    PREFIX="$HOME/.local"
    SYSTEM_INSTALL=0
    echo "=== Installing per-user to $PREFIX ==="
    echo "Run with sudo for udev rules; user install won't grant hidraw/evdev access."
fi

install_dir="$PREFIX/share/mx4control"
bin_dir="$PREFIX/bin"
desktop_dir="$PREFIX/share/applications"

mkdir -p "$install_dir" "$bin_dir" "$desktop_dir"

# Install the Python package
rm -rf "$install_dir/src"
cp -r "$SCRIPT_DIR/src" "$install_dir/"

# Compile .pyc so runtime startup is fast
/usr/bin/python3 -m compileall -q "$install_dir/src" || true

# Three launchers: daemon, CLI, settings GUI
for entry in mx4d:mx4.daemon.main mx4ctl:mx4.cli.main mx4-settings:mx4.ui.app; do
    name="${entry%%:*}"
    module="${entry##*:}"
    cat > "$bin_dir/$name" <<LAUNCH
#!/bin/bash
export PYTHONPATH="$install_dir/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec env LD_PRELOAD="\${LD_PRELOAD:-/usr/lib/libgtk4-layer-shell.so}" \\
    /usr/bin/python3 -m $module "\$@"
LAUNCH
    chmod +x "$bin_dir/$name"
done

# Desktop entry
install -Dm644 "$SCRIPT_DIR/data/io.github.mx4control.desktop" "$desktop_dir/"

# systemd user unit
if [[ $SYSTEM_INSTALL -eq 1 ]]; then
    install -Dm644 "$SCRIPT_DIR/systemd/mx4d.service" \
        /etc/systemd/user/mx4d.service
    echo "Installed systemd user unit → enable per-user with:"
    echo "  systemctl --user daemon-reload"
    echo "  systemctl --user enable --now mx4d.service"

    install -Dm644 "$SCRIPT_DIR/systemd/42-mx4control.rules" \
        /etc/udev/rules.d/42-mx4control.rules
    udevadm control --reload-rules
    udevadm trigger
    echo "udev rules installed and reloaded."
else
    user_unit_dir="$HOME/.config/systemd/user"
    mkdir -p "$user_unit_dir"
    # Swap the system path for the user-local bin in the unit
    sed "s|/usr/local/bin/mx4d|$bin_dir/mx4d|" \
        "$SCRIPT_DIR/systemd/mx4d.service" \
        > "$user_unit_dir/mx4d.service"
    echo "Installed user systemd unit → enable with:"
    echo "  systemctl --user daemon-reload"
    echo "  systemctl --user enable --now mx4d.service"
    echo
    echo "⚠  For hidraw/evdev access run once with sudo:"
    echo "  sudo install -m644 $SCRIPT_DIR/systemd/42-mx4control.rules /etc/udev/rules.d/"
    echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
fi

echo
echo "Done. Test with: mx4ctl ping"
