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

        # Gesture state
        self._gesture_active = False
        self._gesture_start_time = 0.0
        self._accumulated_dx = 0
        self._accumulated_dy = 0
        self._current_direction = GestureDirection.NONE

        # HID++ feature index for REPROG_CONTROLS_V4
        self._reprog_feature_index = None

        # Device grab state
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
            print(">>> evdev module not available")
            logger.error("evdev module not available")
            return None

        candidates = []
        devices_found = evdev.list_devices()
        print(f">>> Scanning {len(devices_found)} evdev devices...")

        for path in devices_found:
            try:
                device = evdev.InputDevice(path)
                name = device.name.lower()

                # Look for MX Master 4 specifically
                if "mx master 4" in name:
                    print(f">>> Found MX Master 4 at {path}: {device.name}")
                    logger.info(f"Found MX Master 4 evdev at {path}: {device.name}")
                    return device

                # Check for Logitech mice via Bolt/Unifying receiver
                if "logitech" in name and "mouse" in name:
                    caps = device.capabilities()
                    if ecodes.EV_REL in caps:
                        rel_caps = caps[ecodes.EV_REL]
                        if ecodes.REL_X in rel_caps and ecodes.REL_Y in rel_caps:
                            print(f">>> Found Logitech mouse at {path}: {device.name}")
                            candidates.append((len(rel_caps), device))

                # Also check for generic "USB Receiver Mouse"
                if "usb receiver" in name and "mouse" in name:
                    caps = device.capabilities()
                    if ecodes.EV_REL in caps:
                        rel_caps = caps[ecodes.EV_REL]
                        if ecodes.REL_X in rel_caps and ecodes.REL_Y in rel_caps:
                            print(f">>> Found USB Receiver mouse at {path}: {device.name}")
                            candidates.append((len(rel_caps), device))

            except PermissionError:
                print(f">>> Permission denied: {path}")
                logger.debug(f"Permission denied for {path}")
                continue
            except Exception as e:
                print(f">>> Error checking {path}: {e}")
                logger.debug(f"Error checking device {path}: {e}")
                continue

        # Return the best candidate
        if candidates:
            candidates.sort(reverse=True, key=lambda x: x[0])
            best = candidates[0][1]
            print(f">>> Selected: {best.path} - {best.name}")
            logger.info(f"Found mouse evdev at {best.path}: {best.name}")
            return best

        print(">>> No matching mouse device found!")
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

        # Set up HID++ button diversion if device is available
        if self._hidpp_device:
            self._setup_hidpp_diversion()
        else:
            logger.warning("No HID++ device set - using evdev button detection (may cause text deselection)")

        self._running = True

        # Start evdev monitoring thread
        self._evdev_thread = threading.Thread(target=self._evdev_monitor_loop, daemon=True)
        self._evdev_thread.start()

        logger.info("Gesture detector started")
        return True

    def _setup_hidpp_diversion(self):
        """Set up HID++ button diversion for the gesture button"""
        from core.hidpp import FeatureID, ControlID

        # TEMPORARILY DISABLED: HID++ diversion isn't receiving notifications properly
        # Fall back to evdev with device grab for now
        print(">>> HID++ button diversion DISABLED - using evdev with grab instead")
        print(">>> (This means the initial button press may briefly affect the OS)")
        return

        try:
            # Get feature index for REPROG_CONTROLS_V4
            self._reprog_feature_index = self._hidpp_device.get_feature_index(FeatureID.REPROG_CONTROLS_V4)
            if self._reprog_feature_index is None:
                logger.warning("Device doesn't support REPROG_CONTROLS_V4")
                return

            # Divert the gesture button
            # Control ID 0x00C3 = Gesture Button
            if self._hidpp_device.divert_button(ControlID.GESTURE_BUTTON, True):
                print(">>> Gesture button DIVERTED via HID++ (won't trigger OS events)")
                logger.info("Gesture button diverted via HID++")
            else:
                logger.warning("Failed to divert gesture button")

            # Also divert BTN_SIDE (Back button) as fallback
            # In case gesture button isn't available
            if self._hidpp_device.divert_button(ControlID.BACK, True):
                print(">>> Back button DIVERTED via HID++ (fallback gesture trigger)")
                logger.info("Back button diverted as fallback")

            # Start HID++ notification listener
            self._hidpp_device.start_notification_listener(self._on_hidpp_notification)

        except Exception as e:
            logger.error(f"Failed to set up HID++ diversion: {e}")
            print(f">>> HID++ diversion setup error: {e}")

    def _on_hidpp_notification(self, feature_index: int, function_id: int, payload: bytes):
        """Handle HID++ notifications (diverted button events)"""
        # Check if this is from REPROG_CONTROLS_V4
        if self._reprog_feature_index and feature_index == self._reprog_feature_index:
            # Function 0 is divertedButtonsEvent
            if function_id == 0:
                self._handle_diverted_button(payload)

    def _handle_diverted_button(self, payload: bytes):
        """Handle diverted button press/release notification"""
        if len(payload) < 4:
            return

        # Payload format: CID (2 bytes) + action (2 bytes)
        # action: 0x0001 = press, 0x0000 = release
        cid = (payload[0] << 8) | payload[1]
        action = (payload[2] << 8) | payload[3]

        from core.hidpp import ControlID

        is_gesture_button = cid in (ControlID.GESTURE_BUTTON, ControlID.BACK)

        if not is_gesture_button:
            return

        if action == 0x0001:  # Press
            print(f">>> HID++ BUTTON PRESSED: CID=0x{cid:04X}")
            self._start_gesture()
        elif action == 0x0000:  # Release
            print(f">>> HID++ BUTTON RELEASED: CID=0x{cid:04X}")
            self._end_gesture()

    def stop(self):
        """Stop the gesture detector"""
        self._running = False

        # Restore button to normal operation
        if self._hidpp_device:
            try:
                from core.hidpp import ControlID
                self._hidpp_device.divert_button(ControlID.GESTURE_BUTTON, False)
                self._hidpp_device.divert_button(ControlID.BACK, False)
                self._hidpp_device.stop_notification_listener()
                print(">>> Button diversion disabled")
            except Exception as e:
                logger.debug(f"Error restoring button: {e}")

        if self._evdev_thread:
            self._evdev_thread.join(timeout=1.0)
            self._evdev_thread = None
        if self._evdev_device:
            self._evdev_device = None

        logger.info("Gesture detector stopped")

    def _evdev_monitor_loop(self):
        """Monitor evdev for mouse movement (runs in background thread)"""
        print(f">>> evdev monitor loop STARTED on {self._evdev_device.path}")
        try:
            for event in self._evdev_device.read_loop():
                if not self._running:
                    break

                # Debug: log button events
                if event.type == ecodes.EV_KEY:
                    print(f">>> EVDEV KEY: code={event.code} value={event.value}")
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
            print(f">>> EVDEV GESTURE BUTTON PRESSED: code={code}")
            # Grab device IMMEDIATELY to prevent further events going to OS
            try:
                self._evdev_device.grab()
                self._device_grabbed = True
                print(">>> Device GRABBED (preventing OS events)")
            except Exception as e:
                print(f">>> Could not grab device: {e}")
                self._device_grabbed = False
            try:
                self._start_gesture()
            except Exception as e:
                print(f">>> Error in gesture start: {e}")
                # If start fails, ungrab immediately
                if self._device_grabbed:
                    try:
                        self._evdev_device.ungrab()
                        print(">>> Device UNGRABBED (after start error)")
                    except:
                        pass
                    self._device_grabbed = False
        elif value == 0:  # Release
            print(f">>> EVDEV GESTURE BUTTON RELEASED: code={code}")
            # CRITICAL: Ungrab device FIRST before any other processing
            # This ensures normal mouse operation is restored even if callbacks fail
            if self._device_grabbed:
                try:
                    self._evdev_device.ungrab()
                    print(">>> Device UNGRABBED")
                except Exception as e:
                    print(f">>> Could not ungrab: {e}")
                finally:
                    self._device_grabbed = False
            # Now safe to process gesture end (callbacks may fail but mouse works)
            try:
                self._end_gesture()
            except Exception as e:
                print(f">>> Error in gesture end: {e}")

    def _handle_evdev_button(self, event):
        """Handle button press/release from evdev (fallback mode)"""
        code = event.code
        value = event.value  # 1=press, 0=release

        # Only print non-left-click buttons
        if value == 1 and code != ecodes.BTN_LEFT:
            print(f">>> EVDEV BUTTON PRESSED: code={code}")

        # Use Back button (BTN_SIDE/275) or Forward button (BTN_EXTRA/276)
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

        print(f">>> EVDEV GESTURE BUTTON: code={code}")

        if value == 1:  # Press
            self._start_gesture()
        elif value == 0:  # Release
            self._end_gesture()

    def _start_gesture(self):
        """Start tracking a gesture"""
        if self._gesture_active:
            return

        self._gesture_active = True
        self._gesture_start_time = time.time()
        self._accumulated_dx = 0
        self._accumulated_dy = 0
        self._current_direction = GestureDirection.CENTER

        logger.debug("Gesture started")
        print(">>> GESTURE STARTED (button press detected)")

        if self.on_gesture_start:
            try:
                self.on_gesture_start()
            except Exception as e:
                print(f">>> ERROR in gesture_start callback: {e}")
                import traceback
                traceback.print_exc()
                logger.error(f"Error in gesture_start callback: {e}")

    def _end_gesture(self):
        """End the current gesture and fire callback"""
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
        print(f">>> GESTURE ENDED: direction={direction.name}, distance={distance:.1f}")

        if self.on_gesture_end:
            try:
                self.on_gesture_end(event)
            except Exception as e:
                print(f">>> ERROR in gesture_end callback: {e}")
                import traceback
                traceback.print_exc()
                logger.error(f"Error in gesture_end callback: {e}")

    def _handle_movement(self, event):
        """Handle relative mouse movement"""
        if not self._gesture_active:
            return

        if event.code == ecodes.REL_X:
            self._accumulated_dx += event.value
        elif event.code == ecodes.REL_Y:
            self._accumulated_dy += event.value

        # Calculate current direction
        new_direction = self._calculate_direction(self._accumulated_dx, self._accumulated_dy)
        self._current_direction = new_direction

        # Always call the callback with current position for smooth 8-segment tracking
        if self.on_gesture_move:
            try:
                self.on_gesture_move(new_direction, self._accumulated_dx, self._accumulated_dy)
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
