"""Inline SVG silhouette of the MX Master 4.

Replaces the hand-drawn Cairo path salad from v1. Rendered at any size
with good anti-aliasing via ``Gdk.Texture.new_from_bytes`` + an
on-the-fly GdkPixbuf. Looks clean at 200 px and at 400 px.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk, GdkPixbuf, GLib

SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 280" width="200" height="280">
  <defs>
    <linearGradient id="body" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2a2a31"/>
      <stop offset="0.55" stop-color="#1b1b20"/>
      <stop offset="1" stop-color="#0f0f12"/>
    </linearGradient>
    <linearGradient id="wheel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#4d4d52"/>
      <stop offset="1" stop-color="#26262b"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.3">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.10"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <!-- body silhouette -->
  <path d="M 50 40
           C 40 15, 160 15, 150 40
           C 170 90, 168 170, 140 220
           C 110 260, 90 258, 70 220
           C 42 175, 30 95, 50 40 Z"
        fill="url(#body)" stroke="#323236" stroke-width="1.2"/>
  <path d="M 50 40
           C 40 15, 160 15, 150 40
           C 170 90, 168 170, 140 220
           C 110 260, 90 258, 70 220
           C 42 175, 30 95, 50 40 Z"
        fill="url(#glow)"/>

  <!-- left / right click split -->
  <path d="M 100 20 L 100 96" stroke="#000" stroke-opacity="0.35" stroke-width="1.1"/>

  <!-- scroll wheel -->
  <rect x="90" y="40" width="20" height="48" rx="5" fill="#0a0a0d"/>
  <rect x="92" y="43" width="16" height="42" rx="3" fill="url(#wheel)"/>
  <g stroke="#000" stroke-opacity="0.35" stroke-width="1">
    <line x1="95" y1="49" x2="105" y2="49"/>
    <line x1="95" y1="56" x2="105" y2="56"/>
    <line x1="95" y1="63" x2="105" y2="63"/>
    <line x1="95" y1="70" x2="105" y2="70"/>
    <line x1="95" y1="77" x2="105" y2="77"/>
  </g>

  <!-- mode-shift button below the wheel -->
  <rect x="94" y="96" width="12" height="7" rx="2" fill="#2d2d32"/>

  <!-- thumb rest texture (dots) -->
  <g fill="#000" fill-opacity="0.22">
    <circle cx="34" cy="150" r="1.4"/>
    <circle cx="42" cy="150" r="1.4"/>
    <circle cx="50" cy="150" r="1.4"/>
    <circle cx="34" cy="160" r="1.4"/>
    <circle cx="42" cy="160" r="1.4"/>
    <circle cx="50" cy="160" r="1.4"/>
    <circle cx="34" cy="170" r="1.4"/>
    <circle cx="42" cy="170" r="1.4"/>
    <circle cx="50" cy="170" r="1.4"/>
  </g>

  <!-- thumb scroll wheel (vertical bar on the side) -->
  <rect x="24" y="130" width="6" height="36" rx="2" fill="#16161a"/>
  <rect x="25" y="132" width="4" height="32" rx="1.5" fill="#35353c"/>

  <!-- side buttons (back / forward) -->
  <rect x="28" y="100" width="18" height="12" rx="3" fill="#1a1a1f"/>
  <rect x="28" y="116" width="18" height="12" rx="3" fill="#1a1a1f"/>

  <!-- gesture thumb button -->
  <rect x="28" y="190" width="28" height="32" rx="6" fill="#16161a"/>
  <g fill="#000" fill-opacity="0.28">
    <circle cx="35" cy="198" r="1"/>
    <circle cx="42" cy="198" r="1"/>
    <circle cx="49" cy="198" r="1"/>
    <circle cx="35" cy="206" r="1"/>
    <circle cx="42" cy="206" r="1"/>
    <circle cx="49" cy="206" r="1"/>
    <circle cx="35" cy="214" r="1"/>
    <circle cx="42" cy="214" r="1"/>
    <circle cx="49" cy="214" r="1"/>
  </g>

  <!-- tiny copper accent -->
  <circle cx="100" cy="158" r="3" fill="#d4a574" fill-opacity="0.38"/>
</svg>
"""


class MouseSVG(Gtk.Picture):
    """Drop-in Gtk.Picture showing the MX Master 4 silhouette."""

    def __init__(self, pixel_size: int = 220):
        super().__init__()
        self.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.set_size_request(pixel_size, int(pixel_size * 280 / 200))
        loader = GdkPixbuf.PixbufLoader.new_with_mime_type("image/svg+xml")
        loader.write(SVG)
        loader.close()
        pixbuf = loader.get_pixbuf()
        if pixbuf:
            self.set_pixbuf(pixbuf)
