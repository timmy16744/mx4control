"""HID++ 2.0 dispatcher.

A single reader thread owns the hidraw fd. Every outgoing request is
tagged with a unique software-identifier (``sw_id``, the low nibble of
the function byte) so the reader can route responses back to the
originating waiter via a per-request ``Event`` + result slot.

Notifications (``sw_id == 0``) are broadcast to registered subscribers
instead of being matched to any pending request.

Why this matters: the previous implementation had two threads racing on
the same fd. The notification listener would occasionally consume the
response to a synchronous request, making the requester time out. A
single reader with sw_id routing eliminates the race entirely.
"""

from __future__ import annotations

import os
import logging
import select
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .features import MessageType, HIDPPError, FeatureID

logger = logging.getLogger(__name__)


REPORT_SHORT = 7
REPORT_LONG = 20
DEFAULT_TIMEOUT_MS = 500
# sw_id 0 is reserved for notifications; 1..15 available for requests
SW_ID_NOTIFICATION = 0
SW_ID_REQUEST_MIN = 1
SW_ID_REQUEST_MAX = 15


# ─────────────────────────── Notification type ────────────────────────────


@dataclass
class Notification:
    """One async HID++ message from the device."""
    device_index: int
    feature_index: int
    function_id: int
    payload: bytes


NotificationHandler = Callable[[Notification], None]


# ─────────────────────────── Request waiter ───────────────────────────────


@dataclass
class _PendingRequest:
    """State for a single in-flight request waiting on a response."""
    sw_id: int
    device_index: int
    feature_index: int
    function_id: int
    event: threading.Event = field(default_factory=threading.Event)
    response: Optional[bytes] = None
    error: Optional[HIDPPError] = None


# ─────────────────────────── Dispatcher ───────────────────────────────────


class HIDPPDispatcher:
    """Owns the hidraw fd and all I/O to it.

    Usage::

        d = HIDPPDispatcher("/dev/hidraw3", device_index=2)
        d.open()
        d.subscribe(handler)       # for async notifications
        response = d.request(feature_index, function_id, *args)
        d.close()
    """

    def __init__(self, hidraw_path: str, device_index: int = 0xFF,
                 timeout_ms: int = DEFAULT_TIMEOUT_MS):
        self._path = hidraw_path
        self._device_index = device_index
        self._timeout = timeout_ms / 1000.0

        self._fd: Optional[int] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

        # sw_id -> _PendingRequest. Guarded by _state_lock.
        self._state_lock = threading.Lock()
        self._pending: dict[int, _PendingRequest] = {}
        self._sw_id_counter = SW_ID_REQUEST_MIN

        # Serializes writes so concatenated bytes from concurrent calls
        # can't interleave on the wire.
        self._write_lock = threading.Lock()

        # Notification subscribers (called on the reader thread — handlers
        # should be fast or hop to their own thread).
        self._subscribers: list[NotificationHandler] = []

        # Feature discovery cache: feature_id -> feature_index
        self._feature_cache: dict[int, int] = {}

    # ─── lifecycle ──────────────────────────────────────────────────────

    def open(self) -> bool:
        if self._fd is not None:
            return True
        try:
            self._fd = os.open(self._path, os.O_RDWR)
        except OSError as e:
            logger.error(f"open({self._path}) failed: {e}")
            return False

        self._running = True
        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="HIDPPReader", daemon=True,
        )
        self._reader_thread.start()

        # Discover features synchronously — the reader is now live and
        # will route the responses to our waiters.
        try:
            self._discover_features()
        except Exception as e:
            logger.warning(f"feature discovery failed: {e}")
            self.close()
            return False

        return True

    def close(self) -> None:
        # Order matters: stop the reader and JOIN it *before* closing the fd.
        # Closing first left a window where the reader could read() a closed
        # (or worse, recycled) fd. The reader polls _running every 0.2s via
        # select() timeout, so the join returns promptly.
        self._running = False
        reader = self._reader_thread
        if reader and reader.is_alive() and reader is not threading.current_thread():
            reader.join(timeout=1.0)
        self._reader_thread = None

        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

        # Wake any pending waiters so they don't block forever
        with self._state_lock:
            for pending in self._pending.values():
                pending.error = HIDPPError(0x01)  # generic
                pending.event.set()
            self._pending.clear()

    @property
    def is_open(self) -> bool:
        return self._fd is not None

    # ─── subscribers ────────────────────────────────────────────────────

    def subscribe(self, handler: NotificationHandler) -> None:
        with self._state_lock:
            if handler not in self._subscribers:
                self._subscribers.append(handler)

    def unsubscribe(self, handler: NotificationHandler) -> None:
        with self._state_lock:
            if handler in self._subscribers:
                self._subscribers.remove(handler)

    # ─── feature lookup ─────────────────────────────────────────────────

    def _discover_features(self) -> None:
        """Enumerate every HID++ feature the device supports.

        Uses ROOT.getFeatureIndex (feature 0x0000, fn 0x00) to find
        FEATURE_SET, then FEATURE_SET.getCount + .getFeatureID to walk
        every available feature by index.
        """
        self._feature_cache.clear()
        self._feature_cache[FeatureID.ROOT] = 0

        # Locate FEATURE_SET via ROOT.getFeatureIndex(0x0001)
        r = self._request_raw(0x00, 0x00, 0x00, 0x01, use_long=False)
        if not r or r[0] == 0:
            raise RuntimeError("FEATURE_SET not present")

        feature_set_idx = r[0]
        self._feature_cache[FeatureID.FEATURE_SET] = feature_set_idx

        # FEATURE_SET.getCount
        r = self._request_raw(feature_set_idx, 0x00, use_long=False)
        if not r:
            raise RuntimeError("FEATURE_SET.getCount failed")

        count = r[0]
        logger.info(f"Device exposes {count} HID++ features")

        # FEATURE_SET.getFeatureID for each index
        for idx in range(count):
            r = self._request_raw(feature_set_idx, 0x01, idx, use_long=False)
            if r and len(r) >= 2:
                feature_id = (r[0] << 8) | r[1]
                self._feature_cache[feature_id] = idx

    def feature_index(self, feature_id: int) -> Optional[int]:
        """Return the feature index for a feature ID, or None if unsupported."""
        return self._feature_cache.get(feature_id)

    def has_feature(self, feature_id: int) -> bool:
        return feature_id in self._feature_cache

    @property
    def feature_cache(self) -> dict[int, int]:
        """Read-only view of all discovered features."""
        return dict(self._feature_cache)

    # ─── request API ────────────────────────────────────────────────────

    def request(self, feature_id: int, function_id: int, *args: int,
                use_long: bool = False, timeout_ms: Optional[int] = None) -> Optional[bytes]:
        """Call a feature's function by feature ID.

        Returns the response payload (bytes after the 4-byte header) or
        ``None`` on timeout. Raises ``HIDPPError`` on device error.
        """
        idx = self.feature_index(feature_id)
        if idx is None:
            logger.debug(f"feature {feature_id:#06x} not supported on this device")
            return None
        return self._request_raw(idx, function_id, *args,
                                 use_long=use_long, timeout_ms=timeout_ms)

    def _request_raw(self, feature_index: int, function_id: int, *args: int,
                     use_long: bool = False,
                     timeout_ms: Optional[int] = None) -> Optional[bytes]:
        """Send a request by feature *index* and wait for the response."""
        if not self.is_open:
            return None

        long_msg = use_long or len(args) > 3
        size = REPORT_LONG if long_msg else REPORT_SHORT
        report_id = MessageType.LONG if long_msg else MessageType.SHORT

        sw_id = self._next_sw_id()
        pending = _PendingRequest(sw_id, self._device_index, feature_index, function_id)
        with self._state_lock:
            self._pending[sw_id] = pending

        try:
            msg = bytearray(size)
            msg[0] = report_id
            msg[1] = self._device_index
            msg[2] = feature_index
            msg[3] = (function_id << 4) | sw_id
            for i, a in enumerate(args):
                if 4 + i < size:
                    msg[4 + i] = a & 0xFF

            timeout = (timeout_ms or DEFAULT_TIMEOUT_MS) / 1000.0
            with self._write_lock:
                os.write(self._fd, bytes(msg))

            if not pending.event.wait(timeout):
                logger.debug(
                    f"timeout feat=0x{feature_index:02x} fn={function_id:#04x}"
                )
                return None

            if pending.error is not None:
                raise pending.error
            return pending.response
        finally:
            with self._state_lock:
                self._pending.pop(sw_id, None)

    # ─── direct raw write (for hidden addresses) ────────────────────────

    def raw_write_short(self, feature_hi: int, feature_lo: int, *data: int) -> bool:
        """Send a 7-byte SHORT message addressed by raw feature bytes.

        Used for the direct-address haptic feature (0x0B4E) which isn't
        in the enumerated feature set but still responds to writes.
        The call is fire-and-forget — we don't wait for a response.
        """
        if not self.is_open:
            return False
        msg = bytearray(REPORT_SHORT)
        msg[0] = MessageType.SHORT
        msg[1] = self._device_index
        msg[2] = feature_hi
        msg[3] = feature_lo  # note: this slot normally holds fn<<4|sw_id
        for i, b in enumerate(data[:3]):
            msg[4 + i] = b & 0xFF
        try:
            with self._write_lock:
                os.write(self._fd, bytes(msg))
            return True
        except OSError:
            return False

    # ─── reader loop ────────────────────────────────────────────────────

    def _next_sw_id(self) -> int:
        with self._state_lock:
            for _ in range(SW_ID_REQUEST_MAX):
                self._sw_id_counter += 1
                if self._sw_id_counter > SW_ID_REQUEST_MAX:
                    self._sw_id_counter = SW_ID_REQUEST_MIN
                if self._sw_id_counter not in self._pending:
                    return self._sw_id_counter
            # All sw_ids taken — very unlikely with only 15 simultaneous
            # requests. Fall back to the counter anyway.
            return self._sw_id_counter

    def _reader_loop(self) -> None:
        """Single reader: routes each message to a waiter or subscribers."""
        while self._running:
            fd = self._fd
            if fd is None:
                break
            try:
                r, _, _ = select.select([fd], [], [], 0.2)
                if not r:
                    continue
                data = os.read(fd, REPORT_LONG)
                if not data or len(data) < 4:
                    continue

                device_idx = data[1]
                feature_idx = data[2]
                function_sw = data[3]
                function_id = (function_sw >> 4) & 0x0F
                sw_id = function_sw & 0x0F
                payload = bytes(data[4:])

                # Ignore messages addressed to other devices on the
                # receiver (we share the hidraw node with every paired
                # device on Bolt)
                if device_idx != self._device_index:
                    continue

                # Error response: feature_idx == 0xFF. Wire layout:
                # [report_id, dev_idx, 0xFF, errored_feat_idx, fn_sw_id, error_code, ...]
                # Note: data[3] (parsed above as function_sw) is errored_feature,
                # and payload = data[4:] begins with [errored_fn_sw, error_code].
                if feature_idx == 0xFF and len(payload) >= 2:
                    errored_feature = data[3]
                    errored_fn_sw = payload[0]
                    error_code = payload[1]
                    errored_sw = errored_fn_sw & 0x0F
                    errored_fn = (errored_fn_sw >> 4) & 0x0F

                    with self._state_lock:
                        pending = self._pending.get(errored_sw)
                    if pending:
                        pending.error = HIDPPError(
                            error_code, errored_feature, errored_fn
                        )
                        pending.event.set()
                    continue

                # Successful response — route to pending request by sw_id
                if sw_id != SW_ID_NOTIFICATION:
                    with self._state_lock:
                        pending = self._pending.get(sw_id)
                    if pending and pending.feature_index == feature_idx:
                        pending.response = payload
                        pending.event.set()
                        continue
                    # Unmatched response — log and drop
                    logger.debug(
                        f"orphan response sw={sw_id} feat={feature_idx}"
                    )
                    continue

                # Async notification
                note = Notification(device_idx, feature_idx, function_id, payload)
                with self._state_lock:
                    subs = list(self._subscribers)
                for h in subs:
                    try:
                        h(note)
                    except Exception as e:
                        logger.error(f"notification handler raised: {e}")

            except OSError as e:
                if self._running:
                    logger.error(f"hidraw read error: {e}")
                    time.sleep(0.1)
            except Exception as e:
                if self._running:
                    logger.exception(f"reader loop error: {e}")
                    time.sleep(0.1)
