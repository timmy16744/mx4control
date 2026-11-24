"""mx4-sysd — the root system daemon.

Owns the HID++ connection to the MX Master 4, applies persistent device
settings on connect (even at the login screen), and exposes the
``org.mx4control.System`` D-Bus service. No GTK / Wayland / evdev here.
"""
