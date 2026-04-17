"""Discover a connected MX Master 4 and return its hidraw path.

Handles two transports:
1. Direct Bluetooth pairing — the mouse enumerates directly under the
   Logitech VID with an MX Master 4 PID. Read/write goes straight to
   device_index 0xFF.
2. Bolt receiver — the mouse is paired to a Bolt USB receiver (PID
   0xC548). We walk the receiver's HID++ 1.0 pairing registers to find
   which slot (1..6) the MX4 is in, and use that as the device_index.

MX Master 4 does NOT enumerate a second USB device when plugged into a
USB-C cable — the cable only charges the device; communication stays
wireless. Confirmed with ``lsusb`` against real hardware.
"""

from __future__ import annotations

import os
import glob
import logging
import select
from typing import Optional

try:
    import hid  # type: ignore[import-untyped]
except ImportError:
    hid = None  # type: ignore[assignment]

from .features import LOGITECH_VID, MX_MASTER_4_PIDS

logger = logging.getLogger(__name__)

BOLT_RECEIVER_PID = 0xC548
UNIFYING_RECEIVER_PID = 0xC52B


def find_mx_master_4() -> Optional[dict]:
    """Return ``dict(path, product_id, device_index, connection_type, ...)``
    describing a reachable MX Master 4, or None.
    """
    # 1. Direct Bluetooth / USB enumeration
    if hid is not None:
        for dev in hid.enumerate(LOGITECH_VID):
            if dev["product_id"] in MX_MASTER_4_PIDS:
                return {
                    "path": dev["path"].decode() if isinstance(dev["path"], bytes) else dev["path"],
                    "product_id": dev["product_id"],
                    "product_string": dev.get("product_string")
                        or MX_MASTER_4_PIDS[dev["product_id"]],
                    "device_index": 0xFF,
                    "connection_type": "bluetooth",
                }

    # 2. Bolt receiver — scan paired slots via HID++ 1.0 registers
    bolt_hidraw = _find_receiver_hidraw(BOLT_RECEIVER_PID)
    if bolt_hidraw:
        for slot, pid in _enumerate_bolt_slots(bolt_hidraw):
            if pid in MX_MASTER_4_PIDS:
                return {
                    "path": bolt_hidraw,
                    "product_id": pid,
                    "product_string": MX_MASTER_4_PIDS[pid],
                    "device_index": slot,
                    "connection_type": "bolt",
                }

    return None


# ─────────────────────────────── helpers ─────────────────────────────────


def _find_receiver_hidraw(product_id: int, interface: int = 2) -> Optional[str]:
    """Find the hidraw node for a Logitech receiver's HID++ interface."""
    target = f"0003:0000046D:{product_id:08X}".upper()
    for hidraw in glob.glob("/sys/class/hidraw/hidraw*"):
        uevent = os.path.join(hidraw, "device", "uevent")
        if not os.path.exists(uevent):
            continue
        try:
            with open(uevent) as f:
                contents = f.read().upper()
        except OSError:
            continue
        if target not in contents:
            continue
        if f"INPUT{interface}" in contents:
            return "/dev/" + os.path.basename(hidraw)
    return None


def _enumerate_bolt_slots(hidraw_path: str) -> list[tuple[int, int]]:
    """Return (slot_number, product_id) for each paired device on the Bolt."""
    out: list[tuple[int, int]] = []
    try:
        fd = os.open(hidraw_path, os.O_RDWR)
    except OSError:
        return out

    def send_recv(msg: bytes, timeout: float = 0.3) -> Optional[bytes]:
        try:
            os.write(fd, msg)
            r, _, _ = select.select([fd], [], [], timeout)
            if r:
                return os.read(fd, 64)
        except OSError:
            return None
        return None

    try:
        # HID++ 1.0 getRegister(0xB5, param=0x5N) reads BOLT_PAIRING_INFO
        # for device slot N (1–6).
        for slot in range(1, 7):
            param = 0x50 + slot
            msg = bytes([0x10, 0xFF, 0x83, 0xB5, param, 0x00, 0x00])
            resp = send_recv(msg)
            if not resp or len(resp) < 12 or resp[2] == 0x8F:
                continue
            data = resp[5:]
            if len(data) < 3:
                continue
            # Little-endian WPID
            wpid = (data[2] << 8) | data[1]
            out.append((slot, wpid))
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

    return out
