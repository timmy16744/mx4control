"""mx4control — Logitech MX Master 4 control suite for Linux/Wayland.

Architecture::

    mx4.hidpp     Low-level HID++ 2.0 protocol (dispatcher, features, device).
    mx4.daemon    Long-running service that owns the hidraw fd and runs the
                  gesture/Actions-Ring engine. Exposes a Unix-socket JSON-RPC API.
    mx4.cli       `mx4ctl` — thin CLI client over the daemon socket.
    mx4.ui        `mx4-settings` — GTK4/libadwaita settings GUI, also a client.
    mx4.config    TOML-backed configuration with migrations.
    mx4.common    Shared helpers (logging, ipc client).

The daemon is the only process that holds an open hidraw fd. All other
processes talk to the daemon via its socket — this lets the settings GUI
and the AGS popup coexist with zero device contention.
"""

__version__ = "2.0.0"
