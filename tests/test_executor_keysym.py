"""Keystroke-parsing regression tests for the agent executor.

These guard the historic bug where the whole shortcut spec was
lowercased, mangling named keysyms (``alt+Left`` → ``alt+left``,
``Page_Up`` → ``page_up``). Only modifier names should be normalised;
the key itself must keep its original case.

Pure-stdlib import — no GTK / Gio / Wayland / D-Bus required.
"""

from __future__ import annotations

import pytest

from mx4.agent.executor import parse_keyspec, wtype_argv, xdotool_argv


@pytest.mark.parametrize("spec,mods,key", [
    ("ctrl+c",          ["ctrl"],            "c"),
    ("alt+Left",        ["alt"],             "Left"),
    ("ctrl+shift+Tab",  ["ctrl", "shift"],   "Tab"),
    ("Page_Up",         [],                  "Page_Up"),
    ("space",           [],                  "space"),
    ("super+1",         ["logo"],            "1"),
    # extra coverage: aliases + named directional keys
    ("alt+Right",       ["alt"],             "Right"),
    ("control+win+Up",  ["ctrl", "logo"],    "Up"),
    ("meta+Down",       ["logo"],            "Down"),
])
def test_parse_keyspec(spec, mods, key):
    got_mods, got_key = parse_keyspec(spec)
    assert got_mods == mods
    assert got_key == key


@pytest.mark.parametrize("spec", ["", "ctrl", "ctrl+shift", "alt+super"])
def test_parse_keyspec_no_key(spec):
    _mods, key = parse_keyspec(spec)
    assert key is None


def test_named_keys_keep_case():
    # The whole point of the fix: named keysyms must NOT be lowercased.
    for spec, expected in [
        ("alt+Left", "Left"),
        ("alt+Right", "Right"),
        ("Page_Up", "Page_Up"),
        ("ctrl+shift+Tab", "Tab"),
        ("Up", "Up"),
        ("Down", "Down"),
    ]:
        _mods, key = parse_keyspec(spec)
        assert key == expected, f"{spec!r} key mangled to {key!r}"
    # ...and single-letter keys stay lowercase as written
    assert parse_keyspec("ctrl+c")[1] == "c"


def test_wtype_argv_builder():
    # alt+Left → press alt, tap Left, release alt
    assert wtype_argv("alt+Left") == [
        "wtype", "-M", "alt", "-k", "Left", "-m", "alt",
    ]
    # ctrl+shift+Tab → press both in order, tap, release in reverse
    assert wtype_argv("ctrl+shift+Tab") == [
        "wtype", "-M", "ctrl", "-M", "shift", "-k", "Tab",
        "-m", "shift", "-m", "ctrl",
    ]
    # ctrl+c
    assert wtype_argv("ctrl+c") == [
        "wtype", "-M", "ctrl", "-k", "c", "-m", "ctrl",
    ]
    # Page_Up — no modifiers
    assert wtype_argv("Page_Up") == ["wtype", "-k", "Page_Up"]
    # space — no modifiers, key kept verbatim
    assert wtype_argv("space") == ["wtype", "-k", "space"]
    # super+1 — modifier normalised to logo
    assert wtype_argv("super+1") == [
        "wtype", "-M", "logo", "-k", "1", "-m", "logo",
    ]


def test_wtype_argv_no_key():
    assert wtype_argv("ctrl+shift") is None
    assert wtype_argv("") is None


def test_xdotool_argv_builder():
    assert xdotool_argv("alt+Left") == ["xdotool", "key", "alt+Left"]
    assert xdotool_argv("ctrl+shift+Tab") == ["xdotool", "key", "ctrl+shift+Tab"]
    assert xdotool_argv("Page_Up") == ["xdotool", "key", "Page_Up"]
    assert xdotool_argv("super+1") == ["xdotool", "key", "logo+1"]
