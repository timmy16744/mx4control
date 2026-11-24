"""Device connection lifecycle: discovery, dispatcher, udev hotplug.

Event-driven, not timer-driven: a ``pyudev`` monitor surfaces hidraw
attach/detach. Discovery + open are idempotent and exception-safe, so a
transient probe error just leaves us waiting for the next udev event
instead of permanently killing reconnect (the old monolith's bug).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from ..hidpp.device import MXMaster4
from ..hidpp.discovery import find_mx_master_4
from ..hidpp.dispatcher import HIDPPDispatcher

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.dispatcher: Optional[HIDPPDispatcher] = None
        self.device: Optional[MXMaster4] = None
        self.info: Optional[dict] = None
        self._observer = None
        self._udev_cb: Optional[Callable[[str, str], None]] = None

    @property
    def connected(self) -> bool:
        return self.device is not None

    def set_udev_callback(self, cb: Callable[[str, str], None]) -> None:
        """cb(action, devnode) is invoked from the udev observer thread."""
        self._udev_cb = cb

    def start_monitor(self) -> bool:
        try:
            import pyudev
        except ImportError:
            logger.warning("pyudev unavailable — hotplug disabled")
            return False
        try:
            ctx = pyudev.Context()
            mon = pyudev.Monitor.from_netlink(ctx)
            mon.filter_by(subsystem="hidraw")
            self._observer = pyudev.MonitorObserver(mon, self._on_udev,
                                                    name="mx4-udev")
            self._observer.start()
            logger.info("udev hidraw monitor started")
            return True
        except Exception as e:
            logger.error("udev monitor failed: %s", e)
            return False

    def _on_udev(self, action, device) -> None:
        if self._udev_cb is None:
            return
        try:
            self._udev_cb(action, getattr(device, "device_node", "") or "")
        except Exception:
            logger.exception("udev callback raised")

    # ─── connect / disconnect ─────────────────────────────────────────────

    def connect(self) -> bool:
        if self.device is not None:
            return True
        try:
            info = find_mx_master_4()
        except Exception as e:
            logger.debug("discovery error: %s", e)
            return False
        if not info:
            return False
        d = HIDPPDispatcher(info["path"], device_index=info["device_index"])
        if not d.open():
            d.close()
            logger.debug("open/discovery failed (mouse asleep or busy?)")
            return False
        self.dispatcher = d
        self.device = MXMaster4(d, info["connection_type"])
        self.info = info
        logger.info("connected: %s (%s, dev_index=%#x) on %s",
                    info["product_string"], info["connection_type"],
                    info["device_index"], info["path"])
        return True

    def disconnect(self) -> None:
        if self.dispatcher is not None:
            try:
                self.dispatcher.close()
            except Exception:
                logger.debug("dispatcher close error", exc_info=True)
        self.dispatcher = None
        self.device = None
        self.info = None

    def alive(self) -> bool:
        """Liveness ping. Call OFF the main loop — it blocks up to ~500ms."""
        try:
            return bool(self.device and self.device.ping())
        except Exception:
            return False

    def stop(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
            except Exception:
                pass
            self._observer = None
        self.disconnect()
