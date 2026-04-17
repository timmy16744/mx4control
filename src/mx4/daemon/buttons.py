"""Button binding service.

Lets any divertable button fire an arbitrary action:

* ``remap``       — firmware-level CID-to-CID remap (no HID++ diversion,
                    just ``setCidReporting`` with a remap target).
* ``keystroke``   — divert the button; on press, synthesise a keystroke.
* ``command``     — divert; run a shell command on press.
* ``application`` — divert; launch an app on press.
* ``disabled``    — divert and ignore presses.
* ``default``     — no diversion, no remap; let the firmware do its thing.

The gesture button is NOT owned by this service — the ``GestureEngine``
already diverts it for the Actions Ring. The ButtonService skips any CID
the gesture engine is managing.
"""

from __future__ import annotations

import logging
import struct
import threading
from dataclasses import dataclass
from typing import Optional

from ..config import ButtonBinding
from ..hidpp import ControlID, FeatureID, MXMaster4
from ..hidpp.dispatcher import Notification
from .executor import execute as execute_action

logger = logging.getLogger(__name__)


@dataclass
class _LiveBinding:
    cid: int
    action_type: str
    action_data: str


class ButtonService:
    """Applies + dispatches user button bindings."""

    def __init__(self, device: MXMaster4, skip_cids: set[int] | None = None):
        self._device = device
        self._dispatcher = device.dispatcher
        self._skip_cids = set(skip_cids or ())  # owned by the gesture engine

        self._live: dict[int, _LiveBinding] = {}  # CID -> active binding
        self._reprog_idx: Optional[int] = None

    # ─── lifecycle ──────────────────────────────────────────────────

    def start(self, bindings: list[ButtonBinding]) -> None:
        self._reprog_idx = self._dispatcher.feature_index(
            FeatureID.REPROG_CONTROLS_V4
        )
        if self._reprog_idx is None:
            logger.info("REPROG_CONTROLS_V4 not supported; bindings disabled")
            return

        self._dispatcher.subscribe(self._on_notification)
        self.apply(bindings)

    def stop(self) -> None:
        # Restore every button we touched
        for cid in list(self._live.keys()):
            self._restore_default(cid)
        self._live.clear()
        self._dispatcher.unsubscribe(self._on_notification)

    # ─── binding application ────────────────────────────────────────

    def apply(self, bindings: list[ButtonBinding]) -> None:
        """Diff against ``self._live`` and apply the new set.

        Idempotent — safe to call any time the user changes config.
        """
        new_by_cid = {b.cid: b for b in bindings if b.cid not in self._skip_cids}

        # Restore buttons that are no longer bound
        for cid in list(self._live.keys()):
            if cid not in new_by_cid:
                self._restore_default(cid)
                self._live.pop(cid, None)

        # Apply new / changed bindings
        for cid, b in new_by_cid.items():
            existing = self._live.get(cid)
            if (existing and existing.action_type == b.action_type
                    and existing.action_data == b.action_data):
                continue
            self._apply_one(b)

    def _apply_one(self, b: ButtonBinding) -> None:
        at = (b.action_type or "default").lower()
        cid = b.cid

        if at == "default":
            self._restore_default(cid)
            self._live.pop(cid, None)
            return

        if at == "remap":
            # Firmware-level remap: no diversion, just change the target.
            try:
                target = int(b.action_data or cid)
            except ValueError:
                target = cid
            self._device.divert_button(cid, False)
            self._device.remap_button(cid, target)
            self._live[cid] = _LiveBinding(cid, at, b.action_data)
            return

        # Everything else (keystroke / command / application / disabled)
        # needs diversion. We also reset any previous firmware remap back
        # to "itself" so the original action doesn't leak through.
        self._device.remap_button(cid, cid)
        if self._device.divert_button(cid, True):
            self._live[cid] = _LiveBinding(cid, at, b.action_data)
        else:
            logger.warning(f"couldn't divert CID 0x{cid:04X}; binding ignored")

    def _restore_default(self, cid: int) -> None:
        # Un-divert and clear any remap
        self._device.divert_button(cid, False)
        self._device.remap_button(cid, cid)

    # ─── HID++ notifications ────────────────────────────────────────

    def _on_notification(self, note: Notification) -> None:
        if note.feature_index != self._reprog_idx:
            return
        if note.function_id != 0:  # divertedButtonsEvent
            return
        if len(note.payload) < 8:
            return
        try:
            cids = struct.unpack(">HHHH", note.payload[:8])
        except struct.error:
            return

        # Find any pressed CIDs that we actually own. We only care about
        # the transition "not-pressed → pressed" so we track last state
        # per CID in instance attr.
        pressed_now = {c for c in cids if c in self._live}
        last_pressed = getattr(self, "_last_pressed", set())

        newly_pressed = pressed_now - last_pressed
        self._last_pressed = pressed_now

        for cid in newly_pressed:
            binding = self._live.get(cid)
            if not binding:
                continue
            self._dispatch(binding)

    def _dispatch(self, b: _LiveBinding) -> None:
        at = b.action_type
        logger.debug(f"dispatching binding: CID 0x{b.cid:04X} -> {at}:{b.action_data}")

        if at == "disabled":
            return  # Button swallowed
        if at == "keystroke":
            threading.Thread(
                target=execute_action,
                args=("keystroke", b.action_data),
                daemon=True,
            ).start()
            return
        if at == "command":
            threading.Thread(
                target=execute_action,
                args=("command", b.action_data),
                daemon=True,
            ).start()
            return
        if at == "application":
            threading.Thread(
                target=execute_action,
                args=("application", b.action_data),
                daemon=True,
            ).start()
            return
