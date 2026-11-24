"""Single dispatcher subscriber for async HID++ 2.0 notifications.

Handles:
* ``REPROG_CONTROLS_V4 (0x1B04)`` fn 0x00 — diverted button press/release sets.
* ``HIRES_WHEEL (0x2121)`` fn 0x00 — diverted high-resolution vertical wheel deltas.
* ``THUMBWHEEL (0x2150)`` fn 0x00 — diverted horizontal thumb-wheel rotation.
* ``WIRELESS_DEVICE_STATUS (0x1D4B)`` fn 0x00 — instant wake / host-switch reconnect.
* ``UNIFIED_BATTERY (0x1004)`` fn 0x00 — live battery & charging updates.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ..hidpp.dispatcher import HIDPPDispatcher, Notification
from ..hidpp.features import FeatureID
from ..hidpp.raw import decode_unified_battery, decode_wireless_status

logger = logging.getLogger(__name__)


class ButtonRouter:
    """Notification router for the system daemon."""

    def __init__(
        self,
        on_diverted: Callable[[list[int]], None],
        on_thumbwheel: Optional[Callable[[int, int], None]] = None,
        on_reconnect: Optional[Callable[[], None]] = None,
        on_battery: Optional[Callable[[int, bool, int, int], None]] = None,
        on_wheel: Optional[Callable[[int, bool], None]] = None,
        on_thumbwheel_packet: Optional[Callable[[int, int, int, int], None]] = None,
    ) -> None:
        self._on_diverted = on_diverted
        self._on_thumbwheel = on_thumbwheel
        self._on_reconnect = on_reconnect
        self._on_battery = on_battery
        self._on_wheel = on_wheel
        self._on_thumbwheel_packet = on_thumbwheel_packet
        self._reprog_index: Optional[int] = None
        self._hires_index: Optional[int] = None
        self._thumb_index: Optional[int] = None
        self._wireless_index: Optional[int] = None
        self._battery_index: Optional[int] = None

    def bind(self, dispatcher: HIDPPDispatcher) -> None:
        self._reprog_index = dispatcher.feature_index(FeatureID.REPROG_CONTROLS_V4)
        self._hires_index = dispatcher.feature_index(FeatureID.HIRES_WHEEL)
        self._thumb_index = dispatcher.feature_index(FeatureID.THUMBWHEEL)
        self._wireless_index = dispatcher.feature_index(0x1D4B)
        self._battery_index = dispatcher.feature_index(FeatureID.UNIFIED_BATTERY)
        dispatcher.subscribe(self._on_notification)

    def _on_notification(self, note: Notification) -> None:
        # 1. Diverted Hi-Res Vertical Wheel (0x2121 fn 0x00) — ultra-low latency hot path
        # Payload: [flags (bit 4 = hi-res), delta_hi, delta_lo]
        if (
            self._on_wheel is not None
            and self._hires_index is not None
            and note.feature_index == self._hires_index
            and note.function_id == 0x00
            and len(note.payload) >= 3
        ):
            hi_res = bool(note.payload[0] & 0x10)
            raw = (note.payload[1] << 8) | note.payload[2]
            if raw >= 0x8000:
                raw -= 0x10000
            if raw != 0:
                try:
                    self._on_wheel(raw, hi_res)
                except Exception:
                    logger.exception("hires wheel callback raised")
            return

        # 2. Diverted buttons (REPROG_CONTROLS_V4 fn 0x00)
        if (
            self._reprog_index is not None
            and note.feature_index == self._reprog_index
            and note.function_id == 0x00
        ):
            cids: list[int] = []
            p = note.payload
            for i in range(0, min(8, len(p) - 1), 2):
                cid = (p[i] << 8) | p[i + 1]
                if cid:
                    cids.append(cid)
            try:
                self._on_diverted(cids)
            except Exception:
                logger.exception("diverted-button callback raised")
            return

        # 2. Diverted thumb wheel (THUMBWHEEL 0x2150 fn 0x00)
        # Payload: [rotation_hi, rotation_lo, timestamp_hi, timestamp_lo, rotation_status, flags]
        if (
            (self._on_thumbwheel is not None or self._on_thumbwheel_packet is not None)
            and self._thumb_index is not None
            and note.feature_index == self._thumb_index
            and note.function_id == 0x00
            and len(note.payload) >= 2
        ):
            raw = (note.payload[0] << 8) | note.payload[1]
            if raw >= 0x8000:
                raw -= 0x10000
            elapsed = ((note.payload[2] << 8) | note.payload[3]) if len(note.payload) >= 4 else 0
            status = note.payload[4] if len(note.payload) >= 5 else 2
            flags = note.payload[5] if len(note.payload) >= 6 else 0
            if raw != 0:
                if self._on_thumbwheel_packet is not None:
                    try:
                        self._on_thumbwheel_packet(raw, elapsed, status, flags)
                    except Exception:
                        logger.exception("thumbwheel packet callback raised")
                if self._on_thumbwheel is not None:
                    direction = 1 if raw > 0 else -1
                    try:
                        self._on_thumbwheel(raw, direction)
                    except Exception:
                        logger.exception("thumbwheel callback raised")
            return

        # 3. Wireless device reconnection (0x1D4B fn 0x00)
        if (
            self._on_reconnect is not None
            and self._wireless_index is not None
            and note.feature_index == self._wireless_index
            and note.function_id == 0x00
        ):
            ws = decode_wireless_status(note.payload)
            if ws and (ws.reconnection or ws.reconf_needed or ws.powered_on):
                try:
                    self._on_reconnect()
                except Exception:
                    logger.exception("reconnect callback raised")
            return

        # 4. Live battery event (UNIFIED_BATTERY 0x1004 fn 0x00)
        if (
            self._on_battery is not None
            and self._battery_index is not None
            and note.feature_index == self._battery_index
            and note.function_id == 0x00
        ):
            ub = decode_unified_battery(note.payload)
            if ub is not None:
                try:
                    self._on_battery(ub.percent, ub.charging, ub.status, ub.level_bucket)
                except Exception:
                    logger.exception("battery callback raised")
