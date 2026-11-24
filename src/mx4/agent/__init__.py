"""mx4-agent — the per-session user agent.

Runs inside the logged-in Wayland session. Owns everything that needs a
display: the evdev-grab gesture engine and the GTK4 / layer-shell Actions
Ring overlay, plus per-application profile resolution. It does **not**
open hidraw — all device I/O goes through the root system daemon
(``org.mx4control.System``) over D-Bus, and the agent drives gestures off
that daemon's ``DivertedButtonEvent`` signal.

The agent owns the session-bus service ``org.mx4control.Agent`` so the
settings GUI can read gesture / profile state.
"""
