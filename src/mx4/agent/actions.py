"""Button-action dispatcher (agent-local).

Turns ``DivertedButtonEvent`` held-CID sets into press/release edges and
dispatches configured software & hardware actions on the rising edge.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from ..config import ButtonBinding
from . import executor
from .executor import HARDWARE_ACTION_TYPES, HardwareHandler

logger = logging.getLogger(__name__)


def diff_pressed(prev: set[int], now: set[int]) -> tuple[set[int], set[int]]:
    """Return ``(newly_pressed, newly_released)`` CID sets."""
    newly_pressed = now - prev
    newly_released = prev - now
    return newly_pressed, newly_released


_SOFTWARE_ACTIONS = {"keystroke", "key_hold", "command", "application"} | set(HARDWARE_ACTION_TYPES)


class ActionDispatcher:
    """Maps diverted-button press & release edges to configured software/hardware actions."""

    def __init__(
        self,
        *,
        bindings_provider: Callable[[], list[ButtonBinding]],
        all_bindings_provider: Optional[Callable[[], list[ButtonBinding]]] = None,
        skip_cids: Optional[set[int]] = None,
        hardware_handler: Optional[HardwareHandler] = None,
        hold_key_fn: Optional[Callable[[int, bool], bool]] = None,
    ):
        self._bindings_provider = bindings_provider
        self._all_bindings_provider = all_bindings_provider
        self._skip_cids = set(skip_cids or ())
        self._hardware_handler = hardware_handler
        self._hold_key_fn = hold_key_fn or executor.hold_key
        self._last_pressed: set[int] = set()
        self._held_keys: dict[int, int] = {}

    def action_bound_cids(self) -> set[int]:
        """CIDs that need diverting to the agent (for the active profile)."""
        divert = _SOFTWARE_ACTIONS | {"disabled"}
        out: set[int] = set()
        for b in self._bindings_provider():
            if b.cid in self._skip_cids:
                continue
            if (b.action_type or "default").lower() in divert:
                out.add(b.cid)
        return out

    def release_all(self) -> None:
        """Release any currently held kernel keys (safety net on disconnect/shutdown)."""
        for cid, code in list(self._held_keys.items()):
            self._held_keys.pop(cid, None)
            try:
                self._hold_key_fn(code, False)
            except Exception:
                logger.debug("release_all failed for key %d", code)
        self._last_pressed.clear()

    def feed_diverted(self, held_cids: set[int]) -> None:
        """Feed the latest held-CID set from the System bus signal."""
        relevant = {c for c in held_cids if c not in self._skip_cids}
        newly_pressed, newly_released = diff_pressed(self._last_pressed, relevant)
        self._last_pressed = relevant

        # Release any held PTT keys immediately on falling edge
        for cid in newly_released:
            code = self._held_keys.pop(cid, None)
            if code is not None:
                logger.debug("releasing held keycode %d (CID 0x%04X)", code, cid)
                threading.Thread(
                    target=self._hold_key_fn, args=(code, False), daemon=True,
                ).start()

        if not newly_pressed:
            return

        by_cid = {b.cid: b for b in self._bindings_provider()}
        for cid in newly_pressed:
            binding = by_cid.get(cid)
            if binding is not None:
                self._dispatch(binding)

    def _dispatch(self, b: ButtonBinding) -> None:
        at = (b.action_type or "default").lower()
        logger.debug("dispatching CID 0x%04X -> %s:%s", b.cid, at, b.action_data)

        if at in ("default", "disabled", "remap"):
            return
        if at == "key_hold":
            code = executor.resolve_evdev_keycode(b.action_data)
            if code is None:
                logger.warning("key_hold: unknown key %r for CID 0x%04X", b.action_data, b.cid)
                return
            self._held_keys[b.cid] = code
            threading.Thread(
                target=self._hold_key_fn, args=(code, True), daemon=True,
            ).start()
            return
        if at in _SOFTWARE_ACTIONS:
            threading.Thread(
                target=executor.execute,
                args=(at, b.action_data, self._hardware_handler),
                daemon=True,
            ).start()
