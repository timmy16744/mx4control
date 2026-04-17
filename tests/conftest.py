"""
Pytest configuration and fixtures for MX4Control tests.
"""

import pytest
import sys
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# Mock GTK/GI modules before any imports that might need them
# ─────────────────────────────────────────────────────────────────────────────

# Create mock gi module
mock_gi = MagicMock()
mock_gi.require_version = MagicMock()

# Create mock Gtk and Adw
mock_gtk = MagicMock()
mock_adw = MagicMock()
mock_gdk = MagicMock()
mock_glib = MagicMock()
mock_gio = MagicMock()
mock_cairo = MagicMock()
mock_pango = MagicMock()

mock_gi.repository = MagicMock()
mock_gi.repository.Gtk = mock_gtk
mock_gi.repository.Adw = mock_adw
mock_gi.repository.Gdk = mock_gdk
mock_gi.repository.GLib = mock_glib
mock_gi.repository.Gio = mock_gio
mock_gi.repository.cairo = mock_cairo
mock_gi.repository.Pango = mock_pango

# Mock evdev
mock_evdev = MagicMock()
mock_evdev.ecodes = MagicMock()
mock_evdev.ecodes.EV_REL = 2
mock_evdev.ecodes.EV_KEY = 1
mock_evdev.ecodes.REL_X = 0
mock_evdev.ecodes.REL_Y = 1
mock_evdev.ecodes.BTN_SIDE = 275
mock_evdev.ecodes.BTN_EXTRA = 276

# Patch modules before any imports
sys.modules['gi'] = mock_gi
sys.modules['gi.repository'] = mock_gi.repository
sys.modules['gi.repository.Gtk'] = mock_gtk
sys.modules['gi.repository.Adw'] = mock_adw
sys.modules['gi.repository.Gdk'] = mock_gdk
sys.modules['gi.repository.GLib'] = mock_glib
sys.modules['gi.repository.Gio'] = mock_gio
sys.modules['gi.repository.cairo'] = mock_cairo
sys.modules['gi.repository.Pango'] = mock_pango
sys.modules['evdev'] = mock_evdev
sys.modules['evdev.ecodes'] = mock_evdev.ecodes
sys.modules['cairo'] = mock_cairo


# ─────────────────────────────────────────────────────────────────────────────
# Config Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory"""
    config_dir = tmp_path / "mx4control"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def config_manager(temp_config_dir):
    """Create a ConfigManager with temporary storage"""
    from core.config import ConfigManager

    config_path = temp_config_dir / "config.json"
    manager = ConfigManager(config_path=config_path)
    return manager


@pytest.fixture
def sample_config():
    """Sample configuration data"""
    return {
        "version": 1,
        "theme": "dark",
        "autostart": False,
        "show_tray_icon": True,
        "start_minimized": False,
        "haptics": {
            "enabled": True,
            "intensity": 2,
            "selected_pattern": 2,
            "notification_pattern": 10,
            "scroll_end_pattern": 3,
            "notification_enabled": True,
            "scroll_end_enabled": False,
            "device_switch_enabled": True,
        },
        "pointer": {
            "dpi": 1600,
            "angle_snapping": False,
            "acceleration": 0.0,
        },
        "scroll": {
            "smartshift_enabled": True,
            "smartshift_threshold": 25,
            "hires_enabled": True,
            "invert_vertical": False,
            "invert_horizontal": False,
        },
        "buttons": [
            {"button_id": 0, "action_type": "default", "action_data": "Left Click"},
            {"button_id": 1, "action_type": "default", "action_data": "Right Click"},
            {"button_id": 2, "action_type": "default", "action_data": "Middle Click"},
        ],
        "actions_ring": {
            "app_pattern": "*",
            "enabled": True,
            "slices": [
                {"position": 0, "label": "Copy", "icon": "", "action_type": "keystroke", "action_data": "ctrl+c"},
                {"position": 1, "label": "Paste", "icon": "", "action_type": "keystroke", "action_data": "ctrl+v"},
            ],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# HID++ Mock Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_hidpp_device():
    """Create a mock HID++ device for testing"""
    device = Mock()
    device.is_open = True
    device._device_index = 0x01
    device._feature_cache = {}

    # Mock successful responses
    device.request = Mock(return_value=bytes([0x00] * 16))
    device.open = Mock(return_value=True)
    device.close = Mock()

    return device


@pytest.fixture
def mock_hidpp_response():
    """Factory for creating mock HID++ responses"""
    def create_response(data: list[int], length: int = 20) -> bytes:
        """Create a response of specified length, padding with zeros"""
        result = bytes(data[:length])
        if len(result) < length:
            result += bytes(length - len(result))
        return result
    return create_response


# ─────────────────────────────────────────────────────────────────────────────
# Gesture Detection Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def gesture_detector():
    """Create a GestureDetector instance for testing"""
    # Mock evdev to avoid hardware requirements
    with patch.dict(sys.modules, {'evdev': Mock()}):
        from services.gesture_detector import GestureDetector
        detector = GestureDetector()
        return detector


@pytest.fixture
def gesture_directions():
    """Test cases for gesture direction calculation

    Direction boundaries (based on atan2 angles):
    - RIGHT: -45 <= angle < 45
    - DOWN: 45 <= angle < 135
    - LEFT: angle >= 135 or angle < -135
    - UP: -135 <= angle < -45
    """
    return [
        # (dx, dy, expected_direction_name)
        (0, -100, "UP"),       # Straight up (-90 degrees)
        (0, 100, "DOWN"),      # Straight down (90 degrees)
        (-100, 0, "LEFT"),     # Straight left (180 degrees)
        (100, 0, "RIGHT"),     # Straight right (0 degrees)
        (0, 0, "CENTER"),      # No movement
        (5, 5, "CENTER"),      # Within deadzone
        (100, -50, "RIGHT"),   # Up-right but more right (~-26 degrees)
        (-100, 50, "LEFT"),    # Down-left but more left (~153 degrees)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Action Executor Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def action_executor():
    """Create an ActionExecutor instance for testing"""
    from services.action_executor import ActionExecutor
    return ActionExecutor()


@pytest.fixture
def sample_actions():
    """Sample action configurations for testing"""
    return [
        ("keystroke", "ctrl+c"),
        ("keystroke", "ctrl+shift+v"),
        ("command", "echo test"),
        ("application", "firefox"),
        ("disabled", ""),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess Mocking
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_subprocess():
    """Mock subprocess for testing command execution"""
    with patch('subprocess.Popen') as mock_popen, \
         patch('subprocess.run') as mock_run:

        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = b""
        mock_process.stderr = b""

        mock_popen.return_value = mock_process
        mock_run.return_value = mock_process

        yield {
            'Popen': mock_popen,
            'run': mock_run,
            'process': mock_process,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Utility Functions
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def write_config_file(temp_config_dir):
    """Helper to write a config file"""
    def _write(data: dict, filename: str = "config.json"):
        config_path = temp_config_dir / filename
        with open(config_path, "w") as f:
            json.dump(data, f)
        return config_path
    return _write
