"""Sidebar navigation list with icon + title + subtitle rows.

Matches the v1 aesthetic: each row has a symbolic icon, a bold title
and a dim subtitle. Selection highlights with the copper accent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


@dataclass(frozen=True)
class NavItem:
    page_id: str
    icon: str
    title: str
    subtitle: str


class SidebarNav(Gtk.ListBox):
    def __init__(self, items: list[NavItem],
                 on_selected: Callable[[str], None]):
        super().__init__()
        self.add_css_class("mx4-nav")
        self.set_selection_mode(Gtk.SelectionMode.SINGLE)

        self._on_selected = on_selected
        self._rows: list[Gtk.ListBoxRow] = []

        for item in items:
            row = Gtk.ListBoxRow()
            row.page_id = item.page_id  # type: ignore[attr-defined]
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                          spacing=12, margin_top=2, margin_bottom=2)
            icon = Gtk.Image.new_from_icon_name(item.icon)
            icon.set_pixel_size(20)
            icon.add_css_class("mx4-nav-icon")
            box.append(icon)

            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                          hexpand=True)
            title = Gtk.Label(label=item.title, xalign=0)
            title.add_css_class("mx4-nav-title")
            col.append(title)
            sub = Gtk.Label(label=item.subtitle, xalign=0)
            sub.add_css_class("mx4-nav-sub")
            col.append(sub)
            box.append(col)

            row.set_child(box)
            self.append(row)
            self._rows.append(row)

        self.connect("row-selected", self._on_row_selected)

        if self._rows:
            self.select_row(self._rows[0])

    def _on_row_selected(self, _box, row):
        if row is not None and self._on_selected:
            self._on_selected(row.page_id)

    def select(self, page_id: str) -> None:
        for r in self._rows:
            if r.page_id == page_id:
                self.select_row(r)
                return
