"""Small shared widget helpers used by multiple pages."""

from __future__ import annotations

from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def section_title(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text.upper(), xalign=0)
    label.add_css_class("mx4-section-title")
    return label


def page_title(text: str, subtitle: str = "") -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    t = Gtk.Label(label=text, xalign=0)
    t.add_css_class("mx4-page-title")
    box.append(t)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0)
        s.add_css_class("mx4-page-subtitle")
        s.set_wrap(True)
        box.append(s)
    return box


def card() -> Gtk.Box:
    c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    c.add_css_class("mx4-card")
    return c


def row_card() -> Gtk.Box:
    c = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    c.add_css_class("mx4-row")
    return c


def setting_row(title: str, subtitle: str = "",
                control: Optional[Gtk.Widget] = None) -> Gtk.Box:
    """Horizontal row with title/subtitle on the left, a control on the
    right. Replaces AdwActionRow because that widget forces a fixed
    narrow title column that wraps labels vertically when a wide suffix
    is attached.
    """
    row = row_card()
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    t = Gtk.Label(label=title, xalign=0)
    t.add_css_class("mx4-row-title")
    col.append(t)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0)
        s.add_css_class("mx4-row-sub")
        s.set_wrap(True)
        col.append(s)
    row.append(col)
    if control is not None:
        control.set_valign(Gtk.Align.CENTER)
        row.append(control)
    return row


def stat_card(label_text: str, value: str, unit: str = "",
              icon: str = "") -> Gtk.Box:
    """Compact status card: icon + small label up top, large value below."""
    c = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    c.add_css_class("mx4-card")

    top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    if icon:
        img = Gtk.Image.new_from_icon_name(icon)
        img.set_pixel_size(14)
        img.set_opacity(0.65)
        top.append(img)
    lbl = Gtk.Label(label=label_text.upper(), xalign=0)
    lbl.add_css_class("mx4-card-unit")
    lbl.set_hexpand(True)
    top.append(lbl)
    c.append(top)

    val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                       valign=Gtk.Align.END)
    val_label = Gtk.Label(label=value, xalign=0)
    val_label.add_css_class("mx4-card-value")
    val_row.append(val_label)
    u = None
    if unit:
        u = Gtk.Label(label=unit, xalign=0, valign=Gtk.Align.END)
        u.add_css_class("mx4-card-unit")
        u.set_margin_bottom(4)
        val_row.append(u)
    c.append(val_row)

    c.value_label = val_label  # type: ignore[attr-defined]
    if u is not None:
        c.unit_label = u       # type: ignore[attr-defined]
    return c
