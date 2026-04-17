"""
Gesture Service

Main service that coordinates gesture detection, the Actions Ring overlay,
and action execution. Runs as a background service within the application.
"""

import gi
gi.require_version("Gtk", "4.0")

from gi.repository import GLib
import logging
import threading
from typing import Optional, Callable

from .gesture_detector import GestureDetector, GestureDirection, GestureEvent
from .actions_ring_overlay import ActionsRingOverlay, RingSegment
from .action_executor import execute_action
from .app_profiles import get_profile_manager, AppProfile

logger = logging.getLogger(__name__)


class GestureService:
    """
    Main gesture service that orchestrates:
    - Gesture detection via HID++ (button) and evdev (movement)
    - Actions Ring overlay display
    - Action execution on gesture completion

    Uses HID++ button diversion for seamless OS integration -
    the gesture button won't trigger any OS-level events.

    All UI updates are marshalled to the main GTK thread via GLib.idle_add.
    """

    def __init__(self):
        self._detector: Optional[GestureDetector] = None
        self._overlay: Optional[ActionsRingOverlay] = None
        self._running = False
        self._enabled = True

        # HID++ device reference (MXMaster4 instance)
        self._hidpp_device = None

        # Configuration
        self._haptic_on_select = True
        self._release_to_select = True

        # Callbacks
        self.on_haptic_trigger: Optional[Callable[[int], None]] = None

        # Config reference
        self._config = None

    def initialize(self, config=None) -> bool:
        """
        Initialize the gesture service.

        Args:
            config: Application configuration object

        Returns:
            True if initialization successful
        """
        self._config = config

        # Create the gesture detector
        self._detector = GestureDetector()
        self._detector.on_gesture_start = self._on_gesture_start
        self._detector.on_gesture_move = self._on_gesture_move
        self._detector.on_gesture_end = self._on_gesture_end

        # Create the overlay (must be done on main thread)
        GLib.idle_add(self._create_overlay)

        logger.info("Gesture service initialized")
        return True

    def _create_overlay(self):
        """Create the overlay window (called on main thread)"""
        self._overlay = ActionsRingOverlay()

        # Haptic tick whenever the highlighted segment changes — gives the
        # ring a tactile feel under the thumb instead of visual-only feedback.
        self._overlay.on_segment_change = self._on_segment_change

        # Load configuration if available
        if self._config:
            self._overlay.load_from_config(self._config)

        return False  # Don't repeat

    def _on_segment_change(self, new_index):
        """Fire a light haptic tick each time the user crosses a ring segment.

        Uses pattern 1 (Light Click) — subtle enough to be pleasant
        during a sweep but noticeable as discrete ticks.
        """
        if not self._haptic_on_select or not self.on_haptic_trigger:
            return
        try:
            self.on_haptic_trigger(1)  # Light click
        except Exception as e:
            logger.debug(f"segment-change haptic failed: {e}")

    def set_hidpp_device(self, device):
        """
        Set the HID++ device for button diversion.

        This should be called after the device connects, before starting
        the gesture service. With HID++, the gesture button won't trigger
        any OS-level events (no text deselection, etc.).

        Args:
            device: MXMaster4 instance
        """
        self._hidpp_device = device
        if self._detector:
            self._detector.set_hidpp_device(device)
            logger.debug(f"HID++ device set for gesture service")

    def start(self) -> bool:
        """Start the gesture service"""
        if self._running:
            return True

        if not self._detector:
            logger.error("Gesture service not initialized")
            return False

        # Pass HID++ device to detector if available
        if self._hidpp_device:
            self._detector.set_hidpp_device(self._hidpp_device)
            logger.info("Starting gesture service with HID++ button diversion")
        else:
            logger.warning("Starting gesture service WITHOUT HID++ - button presses may affect OS")

        if self._detector.start():
            self._running = True
            logger.info("Gesture service started")
            return True

        logger.error("Failed to start gesture detector")
        return False

    def stop(self):
        """Stop the gesture service"""
        self._running = False

        if self._detector:
            self._detector.stop()

        # Hide overlay if visible
        if self._overlay:
            GLib.idle_add(self._hide_overlay)

        logger.info("Gesture service stopped")

    def set_enabled(self, enabled: bool):
        """Enable or disable the gesture service"""
        self._enabled = enabled
        logger.info(f"Gesture service {'enabled' if enabled else 'disabled'}")

    def update_config(self, config):
        """Update service configuration"""
        self._config = config

        if self._overlay and config:
            GLib.idle_add(lambda: self._overlay.load_from_config(config))

        if hasattr(config, 'actions_ring'):
            ring_config = config.actions_ring
            if hasattr(ring_config, 'enabled'):
                self._enabled = ring_config.enabled

    def _on_gesture_start(self):
        """Called when gesture button is pressed (from detector thread)"""
        if not self._enabled:
            logger.warning("Gesture service disabled, ignoring gesture start")
            return

        logger.info("GESTURE STARTED - showing overlay")

        # Get profile for currently focused app
        profile_manager = get_profile_manager()
        profile = profile_manager.get_current_profile()
        logger.debug(f"Gesture started for app: {profile.app_name} ({profile.app_id})")

        # Update overlay with app-specific actions on main thread
        GLib.idle_add(lambda: self._show_overlay_with_profile(profile))

    def _on_gesture_move(self, direction: GestureDirection, dx: int, dy: int):
        """Called during gesture movement (from detector thread)"""
        if not self._enabled or not self._overlay:
            return

        # Update overlay on main thread
        GLib.idle_add(lambda: self._update_overlay(direction, dx, dy))

    def _on_gesture_end(self, event: GestureEvent):
        """Called when gesture button is released (from detector thread)"""
        if not self._enabled:
            return

        logger.debug(f"Gesture ended: {event.direction.name}")

        # Execute action and hide overlay on main thread
        GLib.idle_add(lambda: self._complete_gesture(event))

    def _show_overlay_with_profile(self, profile: AppProfile):
        """Show the overlay with app-specific profile (called on main thread)"""
        try:
            if not self._overlay:
                logger.error("No overlay object available")
                return False

            logger.debug(f"Showing overlay for profile: {profile.app_name} with {len(profile.slices)} slices")

            # Convert profile slices to RingSegments
            segments = []
            for slice in profile.slices:
                segments.append(RingSegment(
                    label=slice.label,
                    icon=slice.icon,
                    action_type=slice.action_type,
                    action_data=slice.action_data
                ))

            # Pad to 8 segments if needed
            while len(segments) < 8:
                segments.append(RingSegment("", "", "disabled", ""))

            # Update and show overlay
            self._overlay.set_segments(segments)
            self._overlay.show_overlay()
        except Exception as e:
            logger.error(f"Error in _show_overlay_with_profile: {e}")
        return False  # Don't repeat

    def _show_overlay(self):
        """Show the overlay window (called on main thread)"""
        if self._overlay:
            self._overlay.show_overlay()
        else:
            logger.error("No overlay object available")
        return False  # Don't repeat

    def _hide_overlay(self):
        """Hide the overlay window (called on main thread)"""
        if self._overlay:
            self._overlay.set_visible(False)
        return False  # Don't repeat

    def _update_overlay(self, direction: GestureDirection, dx: int, dy: int):
        """Update overlay selection (called on main thread)"""
        if self._overlay:
            # Use position-based selection for finer control
            self._overlay.update_from_position(dx, dy)
        return False  # Don't repeat

    def _complete_gesture(self, event: GestureEvent):
        """Complete the gesture and execute action (called on main thread)"""
        if not self._overlay:
            return False

        # Get selected segment and hide overlay
        segment = self._overlay.hide_overlay()

        if segment is None:
            # Cancel zone - no action
            logger.info("Gesture cancelled (center zone)")
            return False

        if segment.action_data and segment.action_type != "disabled":
            logger.info(f"Executing action: {segment.label} ({segment.action_type}: {segment.action_data})")

            # Medium-click confirmation haptic on action execute
            if self._haptic_on_select and self.on_haptic_trigger:
                try:
                    self.on_haptic_trigger(2)
                except Exception as e:
                    logger.debug(f"Haptic trigger failed: {e}")

            # No artificial delay: with HID++ diversion the focused window
            # never lost focus, and the layer-shell overlay never takes it
            # either (KeyboardMode.NONE). wtype can fire immediately.
            result = execute_action(segment.action_type, segment.action_data)
            logger.debug(f"Action result: {result}")
        else:
            logger.debug(f"No action for segment: {segment.label}")

        return False  # Don't repeat

    @property
    def is_running(self) -> bool:
        """Check if service is running"""
        return self._running

    @property
    def device_name(self) -> Optional[str]:
        """Get name of connected device"""
        if self._detector:
            return self._detector.device_name
        return None


# Global service instance with thread-safe initialization
_service: Optional[GestureService] = None
_service_lock = threading.Lock()


def get_gesture_service() -> GestureService:
    """Get or create the global gesture service (thread-safe)"""
    global _service
    if _service is None:
        with _service_lock:
            # Double-check after acquiring lock
            if _service is None:
                _service = GestureService()
    return _service


def start_gesture_service(config=None) -> bool:
    """Initialize and start the gesture service"""
    service = get_gesture_service()
    if service.initialize(config):
        return service.start()
    return False


def stop_gesture_service():
    """Stop the gesture service"""
    if _service:
        _service.stop()
