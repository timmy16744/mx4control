"""MX4Control Background Services"""

from .gesture_detector import GestureDetector, GestureDirection, GestureEvent
from .actions_ring_overlay import ActionsRingOverlay, RingSegment
from .action_executor import ActionExecutor, execute_action, get_executor
from .gesture_service import (
    GestureService,
    get_gesture_service,
    start_gesture_service,
    stop_gesture_service,
)
from .app_profiles import (
    AppProfileManager,
    AppProfile,
    ActionSlice,
    InstalledApp,
    get_profile_manager,
    CATEGORY_TEMPLATES,
)

__all__ = [
    "GestureDetector",
    "GestureDirection",
    "GestureEvent",
    "ActionsRingOverlay",
    "RingSegment",
    "ActionExecutor",
    "execute_action",
    "get_executor",
    "GestureService",
    "get_gesture_service",
    "start_gesture_service",
    "stop_gesture_service",
    "AppProfileManager",
    "AppProfile",
    "ActionSlice",
    "InstalledApp",
    "get_profile_manager",
    "CATEGORY_TEMPLATES",
]
