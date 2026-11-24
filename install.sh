#!/bin/bash
# Install MX4Control 1.0 — system daemon + user agent + CLI + GTK4 settings GUI.
#
# Run with sudo:
#     sudo ./install.sh
#     sudo systemctl enable --now mx4-sysd.service
#     systemctl --user enable --now mx4-agent.service
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "This installs a system service + D-Bus policy + udev rules — run with sudo." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install_dir="/usr/lib/mx4control"
share_dir="/usr/share/mx4control"
LAYER_SHELL="${LAYER_SHELL:-/usr/lib/libgtk4-layer-shell.so}"

echo "=== Installing MX4Control 1.0 to $install_dir ==="
rm -rf "$install_dir/src" "$share_dir/studio"
install -d "$install_dir" "$share_dir/css" "$share_dir/studio"
cp -r "$SCRIPT_DIR/src" "$install_dir/"
install -Dm644 "$SCRIPT_DIR/data/css/style.css" "$share_dir/css/style.css"
cp -r "$SCRIPT_DIR/data/studio/." "$share_dir/studio/"
/usr/bin/python3 -m compileall -q "$install_dir/src" || true

# ── console scripts ───────────────────────────────────────────────────────
emit_launcher() {  # name module [preload]
    local name="$1" module="$2" preload="${3:-}"
    {
        echo '#!/bin/bash'
        echo "export PYTHONPATH=\"$install_dir/src\${PYTHONPATH:+:\$PYTHONPATH}\""
        if [[ -n "$preload" ]]; then
            echo "export LD_PRELOAD=\"\${LD_PRELOAD:-$LAYER_SHELL}\""
        fi
        echo "exec /usr/bin/python3 -m $module \"\$@\""
    } > "/usr/bin/$name"
    chmod +x "/usr/bin/$name"
}
emit_launcher mx4-sysd     mx4.sysd
emit_launcher mx4ctl       mx4.cli.main
emit_launcher mx4-settings mx4.ui.app
emit_launcher mx4-agent    mx4.agent preload

# ── system units / policy / rules ──────────────────────────────────────────
install -Dm644 "$SCRIPT_DIR/systemd/mx4-sysd.service"  /etc/systemd/system/mx4-sysd.service
install -Dm644 "$SCRIPT_DIR/systemd/mx4-agent.service" /usr/lib/systemd/user/mx4-agent.service
install -Dm644 "$SCRIPT_DIR/data/dbus/org.mx4control.System.conf" \
    /usr/share/dbus-1/system.d/org.mx4control.System.conf
install -Dm644 "$SCRIPT_DIR/systemd/42-mx4control.rules" \
    /etc/udev/rules.d/42-mx4control.rules
install -Dm644 "$SCRIPT_DIR/data/io.github.mx4control.desktop" \
    /usr/share/applications/io.github.mx4control.desktop

# ── reload subsystems ──────────────────────────────────────────────────────
systemctl daemon-reload
udevadm control --reload-rules && udevadm trigger
systemctl reload dbus 2>/dev/null || systemctl reload dbus-broker 2>/dev/null || true

if systemctl is-active --quiet mx4-sysd.service; then
    echo "Restarting mx4-sysd.service..."
    systemctl restart mx4-sysd.service
fi

# Automatically restart the invoking desktop user's mx4-agent.service if active!
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    user_uid="$(id -u "$SUDO_USER" 2>/dev/null || true)"
    if [[ -n "$user_uid" && -S "/run/user/$user_uid/bus" ]]; then
        echo "Reloading & restarting mx4-agent.service for $SUDO_USER..."
        sudo -u "$SUDO_USER" \
            XDG_RUNTIME_DIR="/run/user/$user_uid" \
            DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$user_uid/bus" \
            systemctl --user daemon-reload || true
        sudo -u "$SUDO_USER" \
            XDG_RUNTIME_DIR="/run/user/$user_uid" \
            DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$user_uid/bus" \
            systemctl --user restart mx4-agent.service || true
    fi
fi

cat <<'DONE'

Installed MX4Control 1.0 cleanly (mx4-sysd + mx4-agent restarted).
Verify:
  mx4ctl ping
  mx4ctl state
  mx4-settings
DONE
