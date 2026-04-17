"""
Gesture Detector Service

Monitors the MX Master 4 gesture button via HID++ diversion and tracks
mouse movement via evdev for triggering the Actions Ring.

Uses HID++ button diversion so the gesture button doesn't trigger any
OS-level input events (which would deselect text, etc.).
"""

import threading
import logging
import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional
import time

try:
    import evdev
    from evdev import ecodes
except ImportError:
    evdev = None
    ecodes = None

logger = logging.getLogger(__name__)


class GestureDirection(Enum):
    """Gesture movement directions"""
    NONE = auto()
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    CENTER = auto()  # No significant movement


@dataclass
class GestureEvent:
    """Represents a gesture event"""
    direction: GestureDirection
    start_time: float
    end_time: float
    distance: float  # Total movement distance
    dx: int  # Total X movement
    dy: int  # Total Y movement


class GestureDetector:
    """
    Detects gesture button press + mouse movement combinations.

    Uses a hybrid approach:
    - HID++ diversion for gesture button (doesn't trigger OS events)
    - evdev for mouse movement tracking

    When the gesture button is pressed (via HID++), tracks mouse movement
    to determine a direction. Fires callbacks for:
    - gesture_start: When gesture button is pressed
    - gesture_move: During movement while held (with current direction)
    - gesture_end: When released (with final direction)
    """

    # Minimum movement to register a direction (pixels) - very sensitive
    DIRECTION_THRESHOLD = 10

    # Deadzone for center detection - small so it responds quickly
    CENTER_DEADZONE = 8

    def __init__(self):
        self._evdev_device: Optional[evdev.InputDevice] = None
        self._hidpp_device = None  # MXMaster4 instance
        self._running = False
        self._evdev_thread: Optional[threading.Thread] = None

        # Thread-safe gesture state
        self._gesture_lock = threading.Lock()
        self._gesture_active = False
        self._gesture_start_time = 0.0
        self._accumulated_dx = 0
        self._accumulated_dy = 0
        self._current_direction = GestureDirection.NONE

        # HID++ feature index for REPROG_CONTROLS_V4
        self._reprog_feature_index = None

        # Diverted-button state tracking. REPROG_CONTROLS_V4 sends the full
        # set of currently-pressed diverted CIDs in every notification, so we
        # diff against the previous set to derive press/release events.
        self._diverted_pressed: set[int] = set()

        # When True, HID++ button diversion is active and the OS never sees
        # gesture-button events, so we don't need to grab the evdev device.
        self._hidpp_diversion_active = False

        # Device grab state (only used when HID++ diversion isn't available)
        self._device_grabbed = False

        # Callbacks
        self.on_gesture_start: Optional[Callable[[], None]] = None
        self.on_gesture_move: Optional[Callable[[GestureDirection, int, int], None]] = None
        self.on_gesture_end: Optional[Callable[[GestureEvent], None]] = None

    def set_hidpp_device(self, device):
        """
        Set the HID++ device for button diversion.

        Args:
            device: MXMaster4 instance
        """
        self._hidpp_device = device

    def _find_evdev_device(self) -> Optional[evdev.InputDevice]:
        """Find the mouse evdev device for movement tracking"""
        if evdev is None:
            logger.error("evdev module not available")
            return None

        candidates = []
        devices_found = evdev.list_devices()
        logger.debug(f"Scanning {len(devices_found)} evdev devices...")

        for path in devices_found:
            try:
                device = evdev.InputDevice(path)
                name = device.name.lower()

                # Look for MX Master 4 specifically
                if "mx master 4" in name:
                    logger.info(f"Found MX Master 4 evdev at {path}: {device.name}")
                    return device

                # Check for Logitech mice via Bolt/Unifying receiver
                if "logitech" in name and "mouse" in name:
                    caps = device.capabilities()
                    if ecodes.EV_REL in caps:
                        rel_caps = caps[ecodes.EV_REL]
                        if ecodes.REL_X in rel_caps and ecodes.REL_Y in rel_caps:
                            logger.debug(f"Found Logitech mouse at {path}: {device.name}")
                            candidates.append((len(rel_caps), device))

                # Also check for generic "USB Receiver Mouse"
                if "usb receiver" in name and "mouse" in name:
                    caps = device.capabilities()
                    if ecodes.EV_REL in caps:
                        rel_caps = caps[ecodes.EV_REL]
                        if ecodes.REL_X in rel_caps and ecodes.REL_Y in rel_caps:
                            logger.debug(f"Found USB Receiver mouse at {path}: {device.name}")
                            candidates.append((len(rel_caps), device))

            except PermissionError:
                logger.debug(f"Permission denied for {path}")
                continue
            except Exception as e:
                logger.debug(f"Error checking device {path}: {e}")
                continue

        # Return the best candidate
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            best = candidates[0][1]
            logger.info(f"Found mouse evdev at {best.path}: {best.name}")
            return best

        logger.warning("No matching mouse device found")
        return None

    def start(self) -> bool:
        """Start the gesture detector"""
        if self._running:
            return True

        # Find evdev device for movement tracking
        self._evdev_device = self._find_evdev_device()
        if not self._evdev_device:
            logger.error("No evdev mouse device found")
            return False

        # Set up HID++ button diversion if device is available. When active,
        # the OS never sees the gesture-button press so we don't need to
        # grab the evdev device at all.
        self._hidpp_diversion_active = False
        if self._hidpp_device:
            self._hidpp_diversion_active = self._setup_hidpp_diversion()
            if self._hidpp_diversion_active:
                logger.info("Using HID++ diversion for button events (no evdev grab)")
            else:
                logger.warning("HID++ diversion unavailable - falling back to evdev with device grab")
        else:
            logger.warning("No HID++ device set - using evdev button detection (may cause text deselection)")

        self._running = True

        # Start evdev monitoring thread
        self._evdev_thread = threading.Thread(target=self._evdev_monitor_loop, daemon=True)
        self._evdev_thread.start()

        logger.info("Gesture detector started")
        return True

    def _setup_hidpp_diversion(self) -> bool:
        """Set up HID++ button diversion for the gesture button.

        Only diverts the dedicated gesture button. BACK is left alone so
        browser navigation keeps working — we only fall back to diverting
        BACK if this firmware reports the gesture button as non-divertable.

        Returns True if diversion is active (so evdev grab should be skipped).
        """
        from core.hidpp import FeatureID, ControlID

        try:
            self._reprog_feature_index = self._hidpp_device.get_feature_index(FeatureID.REPROG_CONTROLS_V4)
            if self._reprog_feature_index is None:
                logger.warning("Device doesn't support REPROG_CONTROLS_V4 - falling back to evdev grab")
                return False

            if self._hidpp_device.divert_button(ControlID.GESTURE_BUTTON, True):
                logger.info("Gesture button (CID 0x00C3) diverted via HID++")
                self._hidpp_device.start_notification_listener(self._on_hidpp_notification)
                return True

            # Firmware doesn't allow diverting the gesture button — fall back
            # to hijacking BACK. Users lose browser-back on this button until
            # they quit the app, but at least gestures work.
            logger.warning("Gesture button not divertable on this firmware; diverting BACK as fallback")
            if self._hidpp_device.divert_button(ControlID.BACK, True):
                logger.info("Back button (CID 0x0053) diverted as gesture trigger")
                self._hidpp_device.start_notification_listener(self._on_hidpp_notification)
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to set up HID++ diversion: {e}")
            return False

    def _on_hidpp_notification(self, feature_index: int, function_id: int, payload: bytes):
        """Handle HID++ notifications (diverted button events)"""
        if self._reprog_feature_index and feature_index == self._reprog_feature_index:
            # Function 0 is divertedButtonsEvent
            if function_id == 0:
                self._handle_diverted_button(payload)

    def _handle_diverted_button(self, payload: bytes):
        """Handle divertedButtonsEvent.

        Payload is the full set of currently-pressed diverted CIDs as four
        big-endian uint16 values (zero-padded). Press/release is derived by
        diffing against the previously-pressed set.
        """
        import struct
        from core.hidpp import ControlID

        if len(payload) < 8:
            return

        try:
            cids = struct.unpack(">HHHH", payload[:8])
        except struct.error:
            return

        # Only the CIDs we care about participate in gesture start/stop
        trigger_cids = {ControlID.GESTURE_BUTTON, ControlID.BACK}
        now_pressed = {c for c in cids if c in trigger_cids}

        newly_pressed = now_pressed - self._diverted_pressed
        newly_released = self._diverted_pressed - now_pressed
        self._diverted_pressed = now_pressed

        for cid in newly_pressed:
            logger.debug(f"HID++ divert press: CID=0x{cid:04X}")
            self._start_gesture()
            break  # One gesture at a time

        for cid in newly_released:
            logger.debug(f"HID++ divert release: CID=0x{cid:04X}")
            self._end_gesture()
            break

    def stop(self):
        """Stop the gesture detector"""
        self._running = False

        # Restore any buttons we diverted. We don't track which CID we ended
        # up using, so clear both — disabling divert on a never-diverted
        # button is a no-op.
        if self._hidpp_device and self._hidpp_diversion_active:
            try:
                from core.hidpp import ControlID
                self._hidpp_device.stop_notification_listener()
                self._hidpp_device.divert_button(ControlID.GESTURE_BUTTON, False)
                self._hidpp_device.divert_button(ControlID.BACK, False)
                logger.debug("Button diversion disabled")
            except Exception as e:
                logger.debug(f"Error restoring button: {e}")

        self._hidpp_diversion_active = False
        self._diverted_pressed.clear()

        if self._evdev_thread:
            self._evdev_thread.join(timeout=1.0)
            self._evdev_thread = None
        if self._evdev_device:
            self._evdev_device = None

        logger.info("Gesture detector stopped")

    def _evdev_monitor_loop(self):
        """Monitor evdev for mouse movement (runs in background thread).

        When HID++ diversion is active, button events come via HID++
        notifications and we only use evdev for movement. Otherwise we
        fall back to the evdev-with-grab path for button detection.
        """
        logger.debug(f"evdev monitor loop started on {self._evdev_device.path}")
        try:
            for event in self._evdev_device.read_loop():
                if not self._running:
                    break

                if event.type == ecodes.EV_KEY:
                    if not self._hidpp_diversion_active:
                        self._handle_evdev_button_with_grab(event)
                elif event.type == ecodes.EV_REL:
                    self._handle_movement(event)

        except Exception as e:
            if self._running:
                logger.error(f"evdev monitor error: {e}")
        finally:
            self._running = False

    def _handle_evdev_button_with_grab(self, event):
        """Handle button press/release from evdev with device grab to prevent OS events"""
        code = event.code
        value = event.value  # 1=press, 0=release

        # Only care about gesture trigger buttons
        GESTURE_TRIGGER_BUTTONS = {
            ecodes.BTN_SIDE,    # 275 - Back button
            ecodes.BTN_EXTRA,   # 276 - Forward button
        }

        # Accept gesture button codes (277-282)
        is_gesture_button = (
            code in GESTURE_TRIGGER_BUTTONS or
            (code > 276 and code < 300)
        )

        if not is_gesture_button:
            return

        if value == 1:  # Press
            logger.debug(f"Gesture button pressed: code={code}")
            # _start_gesture freezes the cursor via evdev grab itself;
            # _end_gesture unfreezes. We just route the press/release here.
            try:
                self._start_gesture()
            except Exception as e:
                logger.error(f"Error in gesture start: {e}")
                self._unfreeze_cursor()
        elif value == 0:  # Release
            logger.debug(f"Gesture button released: code={code}")
            try:
                self._end_gesture()
            except Exception as e:
                logger.error(f"Error in gesture end: {e}")
                self._unfreeze_cursor()

    def _start_gesture(self):
        """Start tracking a gesture (thread-safe)"""
        with self._gesture_lock:
            if self._gesture_active:
                return

            self._gesture_active = True
            self._gesture_start_time = time.time()
            self._accumulated_dx = 0
            self._accumulated_dy = 0
            self._current_direction = GestureDirection.CENTER

        # Freeze the cursor so the ring stays a stable frame of reference
        # while the user flicks the mouse. Without this the OS cursor drifts
        # across the screen during the gesture.
        self._freeze_cursor()

        logger.debug("Gesture started")

        if self.on_gesture_start:
            try:
                self.on_gesture_start()
            except Exception as e:
                logger.error(f"Error in gesture_start callback: {e}")

    def _freeze_cursor(self):
        """Grab the evdev device so mouse movement stops reaching the OS.

        Idempotent — safe to call even if the evdev-fallback path already
        grabbed the device on the button-down event.
        """
        if self._device_grabbed or not self._evdev_device:
            return
        try:
            self._evdev_device.grab()
            self._device_grabbed = True
            logger.debug("Cursor frozen (evdev grabbed)")
        except Exception as e:
            # Common: device already grabbed by someone else, or permission
            logger.debug(f"Could not grab for cursor freeze: {e}")

    def _unfreeze_cursor(self):
        """Release the evdev grab so the OS resumes receiving movement."""
        if not self._device_grabbed or not self._evdev_device:
            return
        try:
            self._evdev_device.ungrab()
            logger.debug("Cursor unfrozen (evdev released)")
        except Exception as e:
            logger.debug(f"Could not ungrab: {e}")
        finally:
            self._device_grabbed = False

    def _end_gesture(self):
        """End the current gesture and fire callback (thread-safe)"""
        # Release the grab FIRST so the cursor resumes even if the callback
        # chain raises. Users can always recover mouse control this way.
        self._unfreeze_cursor()

        with self._gesture_lock:
            if not self._gesture_active:
                return

            self._gesture_active = False
            end_time = time.time()

            # Calculate final direction
            direction = self._calculate_direction(self._accumulated_dx, self._accumulated_dy)
            distance = math.sqrt(self._accumulated_dx**2 + self._accumulated_dy**2)

            event = GestureEvent(
                direction=direction,
                start_time=self._gesture_start_time,
                end_time=end_time,
                distance=distance,
                dx=self._accumulated_dx,
                dy=self._accumulated_dy,
            )

        logger.debug(f"Gesture ended: {direction.name}, distance={distance:.1f}")

        if self.on_gesture_end:
            try:
                self.on_gesture_end(event)
            except Exception as e:
                logger.error(f"Error in gesture_end callback: {e}")

    def _handle_movement(self, event):
        """Handle relative mouse movement (thread-safe)"""
        with self._gesture_lock:
            if not self._gesture_active:
                return

            if event.code == ecodes.REL_X:
                self._accumulated_dx += event.value
            elif event.code == ecodes.REL_Y:
                self._accumulated_dy += event.value

            # Calculate current direction
            new_direction = self._calculate_direction(self._accumulated_dx, self._accumulated_dy)
            self._current_direction = new_direction
            dx = self._accumulated_dx
            dy = self._accumulated_dy

        # Call callback outside of lock to prevent deadlocks
        if self.on_gesture_move:
            try:
                self.on_gesture_move(new_direction, dx, dy)
            except Exception as e:
                logger.error(f"Error in gesture_move callback: {e}")

    def _calculate_direction(self, dx: int, dy: int) -> GestureDirection:
        """Calculate direction from accumulated movement"""
        distance = math.sqrt(dx*dx + dy*dy)

        if distance < self.CENTER_DEADZONE:
            return GestureDirection.CENTER

        if distance < self.DIRECTION_THRESHOLD:
            return GestureDirection.CENTER

        # Calculate angle (0 = right, 90 = down, etc.)
        angle = math.atan2(dy, dx) * 180 / math.pi

        # Convert to direction (with 45-degree sectors)
        if -45 <= angle < 45:
            return GestureDirection.RIGHT
        elif 45 <= angle < 135:
            return GestureDirection.DOWN
        elif angle >= 135 or angle < -135:
            return GestureDirection.LEFT
        else:  # -135 <= angle < -45
            return GestureDirection.UP

    @property
    def is_running(self) -> bool:
        """Check if detector is running"""
        return self._running

    @property
    def device_name(self) -> Optional[str]:
        """Get connected device name"""
        return self._evdev_device.name if self._evdev_device else None
