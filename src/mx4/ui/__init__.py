"""mx4-settings — GTK4/libadwaita settings GUI.

Thin client over the daemon socket — never opens the hidraw node
directly. Only three pages:

* Overview  — live status (battery, DPI, charging, hosts).
* Actions Ring — configure segments per application with a gesture
  recording mode.
* Advanced — SmartShift, hi-res scroll, thumb wheel diversion. (Most
  other "config" surfaces from v1 are gone because Solaar handles them
  better; we only keep what's uniquely useful here.)
"""
