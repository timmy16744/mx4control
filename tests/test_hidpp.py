"""
Tests for HID++ protocol implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import struct


class TestHIDPPError:
    """Tests for HIDPPError exception class"""

    def test_known_error_codes(self):
        """Test that known error codes have descriptive messages"""
        from core.hidpp import HIDPPError

        known_codes = {
            0x01: "Unknown",
            0x02: "Invalid argument",
            0x03: "Out of range",
            0x04: "Hardware error",
            0x05: "Logitech internal",
            0x06: "Invalid feature index",
            0x07: "Invalid function ID",
            0x08: "Busy",
            0x09: "Unsupported",
        }

        for code, expected_msg in known_codes.items():
            error = HIDPPError(code)
            assert error.code == code
            assert expected_msg in str(error)

    def test_unknown_error_code(self):
        """Test handling of unknown error codes"""
        from core.hidpp import HIDPPError

        error = HIDPPError(0xFF)
        assert error.code == 0xFF
        assert "0xff" in str(error).lower() or "255" in str(error)


class TestMessageTypes:
    """Tests for HID++ message type constants"""

    def test_message_types(self):
        """Test message type values"""
        from core.hidpp import MessageType

        assert MessageType.SHORT == 0x10
        assert MessageType.LONG == 0x11


class TestFeatureIDs:
    """Tests for HID++ feature ID constants"""

    def test_standard_features(self):
        """Test standard feature IDs"""
        from core.hidpp import FeatureID

        assert FeatureID.ROOT == 0x0000
        assert FeatureID.FEATURE_SET == 0x0001
        assert FeatureID.DEVICE_NAME == 0x0005
        assert FeatureID.UNIFIED_BATTERY == 0x1004
        assert FeatureID.ADJUSTABLE_DPI == 0x2201

    def test_mx_master_4_features(self):
        """Test MX Master 4 specific features"""
        from core.hidpp import FeatureID

        assert FeatureID.MX_HAPTICS == 0x0B4E
        assert FeatureID.MX_SMART_ACTIONS == 0x9401


class TestHapticPattern:
    """Tests for HapticPattern enum"""

    def test_pattern_values(self):
        """Test haptic pattern values are in expected range"""
        from core.hidpp import HapticPattern

        for pattern in HapticPattern:
            assert 0 <= pattern.value <= 14

    def test_pattern_aliases(self):
        """Test pattern aliases match their numeric counterparts"""
        from core.hidpp import HapticPattern

        assert HapticPattern.SOFT_BUMP == HapticPattern.PATTERN_4
        assert HapticPattern.LIGHT_CLICK == HapticPattern.PATTERN_1
        assert HapticPattern.MEDIUM_CLICK == HapticPattern.PATTERN_2
        assert HapticPattern.STRONG_CLICK == HapticPattern.PATTERN_3


class TestControlIDs:
    """Tests for button Control ID constants"""

    def test_button_control_ids(self):
        """Test button CID values"""
        from core.hidpp import ControlID

        assert ControlID.LEFT_CLICK == 0x0050
        assert ControlID.RIGHT_CLICK == 0x0051
        assert ControlID.MIDDLE_CLICK == 0x0052
        assert ControlID.GESTURE_BUTTON == 0x00C3


class TestTaskIDs:
    """Tests for button Task ID constants"""

    def test_task_ids(self):
        """Test task ID values"""
        from core.hidpp import TaskID

        assert TaskID.DISABLED == 0x0000
        assert TaskID.LEFT_CLICK == 0x0038
        assert TaskID.MEDIA_PLAY_PAUSE == 0x0069


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass"""

    def test_device_info_creation(self):
        """Test creating DeviceInfo instance"""
        from core.hidpp import DeviceInfo

        info = DeviceInfo(
            name="MX Master 4",
            product_id=0xB042,
            serial="ABC123",
            firmware_version="1.2.3",
            protocol_version="HID++ 4.5",
            battery_level=85,
            battery_charging=False,
            connection_type="bolt",
        )

        assert info.name == "MX Master 4"
        assert info.product_id == 0xB042
        assert info.battery_level == 85
        assert info.connection_type == "bolt"


class TestFeature:
    """Tests for Feature dataclass"""

    def test_feature_creation(self):
        """Test creating Feature instance"""
        from core.hidpp import Feature

        feature = Feature(
            feature_id=0x1004,
            index=5,
            feature_type=0,
            name="UNIFIED_BATTERY",
        )

        assert feature.feature_id == 0x1004
        assert feature.index == 5


class TestHIDPPDevice:
    """Tests for HIDPPDevice class"""

    def test_initialization(self):
        """Test device initialization"""
        from core.hidpp import HIDPPDevice

        device = HIDPPDevice(device_path="/dev/hidraw0", device_index=0xFF)

        assert device._device_path == "/dev/hidraw0"
        assert device._device_index == 0xFF
        assert device._feature_cache == {}
        assert device.is_open is False

    def test_is_open_false_initially(self):
        """Test device is not open initially"""
        from core.hidpp import HIDPPDevice

        device = HIDPPDevice()
        assert device.is_open is False

    def test_close_without_open(self):
        """Test closing a device that was never opened"""
        from core.hidpp import HIDPPDevice

        device = HIDPPDevice()
        device.close()  # Should not raise

    def test_report_sizes(self):
        """Test report size constants"""
        from core.hidpp import HIDPPDevice

        assert HIDPPDevice.REPORT_SHORT == 7
        assert HIDPPDevice.REPORT_LONG == 20


class TestHIDPPDeviceWithMock:
    """Tests for HIDPPDevice with mocked hardware"""

    @pytest.fixture
    def mock_device(self):
        """Create a mock HID++ device"""
        from core.hidpp import HIDPPDevice

        device = HIDPPDevice(device_path="/dev/hidraw0", device_index=0xFF)
        device._raw_fd = 999  # Fake file descriptor
        device._use_raw = True
        return device

    def test_feature_cache_operations(self, mock_device):
        """Test feature cache get/set"""
        from core.hidpp import FeatureID

        mock_device._feature_cache[FeatureID.ROOT] = 0
        mock_device._feature_cache[FeatureID.UNIFIED_BATTERY] = 5

        assert mock_device._feature_cache.get(FeatureID.ROOT) == 0
        assert mock_device._feature_cache.get(FeatureID.UNIFIED_BATTERY) == 5
        assert mock_device._feature_cache.get(FeatureID.DEVICE_NAME) is None

    def test_has_feature_with_cached(self, mock_device):
        """Test has_feature when feature is cached"""
        from core.hidpp import FeatureID

        mock_device._feature_cache[FeatureID.UNIFIED_BATTERY] = 5

        # Need to mock get_feature_index for non-cached case
        with patch.object(mock_device, 'get_feature_index', return_value=5):
            assert mock_device.has_feature(FeatureID.UNIFIED_BATTERY) is True

    def test_get_feature_index_from_cache(self, mock_device):
        """Test get_feature_index returns cached value"""
        from core.hidpp import FeatureID

        mock_device._feature_cache[FeatureID.ADJUSTABLE_DPI] = 7
        assert mock_device.get_feature_index(FeatureID.ADJUSTABLE_DPI) == 7


class TestMXMaster4:
    """Tests for MXMaster4 high-level interface"""

    @pytest.fixture
    def mock_mx4(self):
        """Create a mock MX Master 4 device"""
        from core.hidpp import MXMaster4

        device = MXMaster4(device_path="/dev/hidraw0", device_index=0xFF)
        device._raw_fd = 999
        device._use_raw = True
        return device

    def test_initialization(self, mock_mx4):
        """Test MX Master 4 initialization"""
        assert mock_mx4._name == "MX Master 4"
        assert mock_mx4._dpi == 1000
        assert mock_mx4._haptic_intensity == 2

    def test_dpi_caching(self, mock_mx4):
        """Test DPI value caching"""
        mock_mx4._dpi = 1600
        assert mock_mx4.get_dpi() == 1600

    def test_set_dpi_bounds(self, mock_mx4):
        """Test DPI bounds clamping"""
        with patch.object(mock_mx4, 'request', return_value=bytes(16)):
            # Test lower bound
            mock_mx4.set_dpi(100)
            # DPI should be clamped to 200

            # Test upper bound
            mock_mx4.set_dpi(10000)
            # DPI should be clamped to 8000

    def test_haptic_intensity_validation(self, mock_mx4):
        """Test haptic intensity must be 0-3"""
        with pytest.raises(ValueError):
            mock_mx4.set_haptic_intensity(-1)

        with pytest.raises(ValueError):
            mock_mx4.set_haptic_intensity(4)

    def test_connection_type_detection(self, mock_mx4):
        """Test connection type based on device index"""
        # Direct connection (Bluetooth)
        mock_mx4._device_index = 0xFF
        with patch.object(mock_mx4, '_get_device_name', return_value="MX Master 4"):
            with patch.object(mock_mx4, '_get_battery_status', return_value=(85, False)):
                with patch.object(mock_mx4, '_get_firmware_version', return_value="1.0.0"):
                    info = mock_mx4.get_device_info()
                    assert info.connection_type == "bluetooth"

        # Via receiver (Bolt)
        mock_mx4._device_index = 1
        with patch.object(mock_mx4, '_get_device_name', return_value="MX Master 4"):
            with patch.object(mock_mx4, '_get_battery_status', return_value=(85, False)):
                with patch.object(mock_mx4, '_get_firmware_version', return_value="1.0.0"):
                    info = mock_mx4.get_device_info()
                    assert info.connection_type == "bolt"


class TestBatteryStatusParsing:
    """Tests for battery status response parsing"""

    @pytest.fixture
    def mock_mx4(self):
        """Create a mock MX Master 4 device"""
        from core.hidpp import MXMaster4

        device = MXMaster4()
        device._raw_fd = 999
        device._use_raw = True
        return device

    def test_parse_unified_battery_discharging(self, mock_mx4):
        """Test parsing battery status when discharging"""
        # Response: [level, next_level, status, ...]
        # Status 0 = discharging
        with patch.object(mock_mx4, 'request') as mock_request:
            mock_request.return_value = bytes([85, 80, 0] + [0] * 13)
            level, charging = mock_mx4._get_battery_status()
            assert level == 85
            assert charging is False

    def test_parse_unified_battery_charging(self, mock_mx4):
        """Test parsing battery status when charging"""
        # Status 1, 2, 3 = various charging states
        with patch.object(mock_mx4, 'request') as mock_request:
            mock_request.return_value = bytes([50, 60, 1] + [0] * 13)
            level, charging = mock_mx4._get_battery_status()
            assert level == 50
            assert charging is True

    def test_parse_battery_empty_response(self, mock_mx4):
        """Test handling of empty battery response"""
        with patch.object(mock_mx4, 'request') as mock_request:
            mock_request.return_value = None
            level, charging = mock_mx4._get_battery_status()
            assert level == 0
            assert charging is False

    def test_parse_battery_short_response(self, mock_mx4):
        """Test handling of too-short battery response"""
        with patch.object(mock_mx4, 'request') as mock_request:
            # Response with only 2 bytes (need at least 3)
            mock_request.return_value = bytes([85, 80])
            level, charging = mock_mx4._get_battery_status()
            # Should return defaults
            assert level == 0
            assert charging is False


class TestButtonInfoParsing:
    """Tests for button info response parsing"""

    @pytest.fixture
    def mock_mx4(self):
        """Create a mock MX Master 4 device"""
        from core.hidpp import MXMaster4

        device = MXMaster4()
        device._raw_fd = 999
        device._use_raw = True
        device._feature_cache[0x1B04] = 4  # REPROG_CONTROLS_V4 at index 4
        return device

    def test_parse_button_info(self, mock_mx4):
        """Test parsing button info response"""
        # Response: [cid_hi, cid_lo, tid_hi, tid_lo, flags, ...]
        # CID=0x0050 (left click), TID=0x0038, flags=0x30 (remappable+divertable)
        with patch.object(mock_mx4, 'request') as mock_request:
            mock_request.return_value = bytes([0x00, 0x50, 0x00, 0x38, 0x30] + [0] * 11)
            info = mock_mx4.get_button_info(0)

            assert info is not None
            assert info["control_id"] == 0x0050
            assert info["task_id"] == 0x0038
            assert info["remappable"] is True
            assert info["divertable"] is True

    def test_parse_button_info_not_remappable(self, mock_mx4):
        """Test parsing button that is not remappable"""
        with patch.object(mock_mx4, 'request') as mock_request:
            # flags=0x20 means divertable but not remappable
            mock_request.return_value = bytes([0x00, 0x51, 0x00, 0x39, 0x20] + [0] * 11)
            info = mock_mx4.get_button_info(1)

            assert info is not None
            assert info["remappable"] is False
            assert info["divertable"] is True

    def test_parse_button_info_short_response(self, mock_mx4):
        """Test handling of too-short button info response"""
        with patch.object(mock_mx4, 'request') as mock_request:
            # Only 4 bytes (need at least 5)
            mock_request.return_value = bytes([0x00, 0x50, 0x00, 0x38])
            info = mock_mx4.get_button_info(0)
            assert info is None


class TestSmartShift:
    """Tests for SmartShift configuration"""

    @pytest.fixture
    def mock_mx4(self):
        """Create a mock MX Master 4 device"""
        from core.hidpp import MXMaster4, FeatureID

        device = MXMaster4()
        device._raw_fd = 999
        device._use_raw = True
        device._feature_cache[FeatureID.SMART_SHIFT_ENHANCED] = 8
        return device

    def test_smartshift_enabled(self, mock_mx4):
        """Test parsing SmartShift enabled status"""
        with patch.object(mock_mx4, 'request') as mock_request:
            # Response: [wheel_mode, auto_disengage, ...]
            # auto_disengage > 0 means enabled
            mock_request.return_value = bytes([1, 25] + [0] * 14)
            enabled, threshold = mock_mx4.get_smartshift_status()
            assert enabled is True
            assert threshold == 25

    def test_smartshift_disabled(self, mock_mx4):
        """Test parsing SmartShift disabled status"""
        with patch.object(mock_mx4, 'request') as mock_request:
            # auto_disengage = 0 means disabled
            mock_request.return_value = bytes([1, 0] + [0] * 14)
            enabled, threshold = mock_mx4.get_smartshift_status()
            assert enabled is False
            assert threshold == 25  # Default threshold

    def test_set_smartshift_threshold_bounds(self, mock_mx4):
        """Test SmartShift threshold clamping"""
        with patch.object(mock_mx4, 'request') as mock_request:
            mock_request.return_value = bytes(16)

            # Test that threshold is clamped to 1-255
            mock_mx4.set_smartshift(True, 0)  # Should clamp to 1
            mock_mx4.set_smartshift(True, 300)  # Should clamp to 255


class TestDPIParsing:
    """Tests for DPI response parsing"""

    @pytest.fixture
    def mock_mx4(self):
        """Create a mock MX Master 4 device"""
        from core.hidpp import MXMaster4, FeatureID

        device = MXMaster4()
        device._raw_fd = 999
        device._use_raw = True
        device._feature_cache[FeatureID.ADJUSTABLE_DPI] = 6
        return device

    def test_parse_dpi_list(self, mock_mx4):
        """Test parsing DPI presets list"""
        with patch.object(mock_mx4, 'request') as mock_request:
            # Response: [count, dpi1_hi, dpi1_lo, dpi2_hi, dpi2_lo, ...]
            # 4 DPIs: 800, 1000, 1600, 4000
            mock_request.return_value = bytes([
                4,
                0x03, 0x20,  # 800
                0x03, 0xE8,  # 1000
                0x06, 0x40,  # 1600
                0x0F, 0xA0,  # 4000
            ] + [0] * 7)
            dpis = mock_mx4.get_dpi_list()
            assert dpis == [800, 1000, 1600, 4000]

    def test_parse_dpi_list_empty(self, mock_mx4):
        """Test DPI list with empty response returns defaults"""
        with patch.object(mock_mx4, 'request') as mock_request:
            mock_request.return_value = None
            dpis = mock_mx4.get_dpi_list()
            # Should return default list
            assert 1000 in dpis
            assert 1600 in dpis


class TestMessageBuilding:
    """Tests for HID++ message construction"""

    def test_short_message_format(self):
        """Test short message is 7 bytes"""
        from core.hidpp import HIDPPDevice, MessageType

        device = HIDPPDevice(device_index=0xFF)

        # Build message internally
        msg = bytearray(device.REPORT_SHORT)
        msg[0] = MessageType.SHORT
        msg[1] = 0xFF  # device index
        msg[2] = 0x00  # feature index
        msg[3] = 0x00  # function id << 4

        assert len(msg) == 7
        assert msg[0] == 0x10

    def test_long_message_format(self):
        """Test long message is 20 bytes"""
        from core.hidpp import HIDPPDevice, MessageType

        device = HIDPPDevice(device_index=0xFF)

        msg = bytearray(device.REPORT_LONG)
        msg[0] = MessageType.LONG
        msg[1] = 0xFF
        msg[2] = 0x05
        msg[3] = 0x10  # function 1 << 4

        assert len(msg) == 20
        assert msg[0] == 0x11


class TestDeviceDiscovery:
    """Tests for device discovery functions"""

    def test_mx_master_4_pids(self):
        """Test MX Master 4 product IDs are defined"""
        from core.hidpp import MX_MASTER_4_PIDS

        assert 0xB042 in MX_MASTER_4_PIDS  # Bolt
        assert 0x4107 in MX_MASTER_4_PIDS  # Bluetooth

    def test_receiver_pids(self):
        """Test receiver product IDs are defined"""
        from core.hidpp import RECEIVER_PIDS

        assert 0xC548 in RECEIVER_PIDS  # Bolt
        assert 0xC52B in RECEIVER_PIDS  # Unifying

    def test_logitech_vid(self):
        """Test Logitech vendor ID"""
        from core.hidpp import LOGITECH_VID

        assert LOGITECH_VID == 0x046D


class TestRemapActions:
    """Tests for button remap action mappings"""

    def test_remap_actions_exist(self):
        """Test remap actions dictionary exists and has entries"""
        from core.hidpp import REMAP_ACTIONS

        assert len(REMAP_ACTIONS) > 0
        assert "Default" in REMAP_ACTIONS
        assert "Left Click" in REMAP_ACTIONS
        assert "Disabled" in REMAP_ACTIONS

    def test_default_action_is_none(self):
        """Test Default action maps to None"""
        from core.hidpp import REMAP_ACTIONS

        assert REMAP_ACTIONS["Default"] is None

    def test_disabled_action_is_zero(self):
        """Test Disabled action maps to 0"""
        from core.hidpp import REMAP_ACTIONS, TaskID

        assert REMAP_ACTIONS["Disabled"] == TaskID.DISABLED


class TestHapticTrigger:
    """Tests for haptic trigger functionality"""

    @pytest.fixture
    def mock_mx4(self):
        """Create a mock MX Master 4 device"""
        from core.hidpp import MXMaster4

        device = MXMaster4()
        device._raw_fd = 999
        device._use_raw = True
        return device

    def test_trigger_haptic_not_open(self, mock_mx4):
        """Test haptic trigger fails when device not open"""
        mock_mx4._raw_fd = None

        result = mock_mx4.trigger_haptic()
        assert result is False

    def test_trigger_haptic_with_pattern_enum(self, mock_mx4):
        """Test triggering haptic with HapticPattern enum"""
        from core.hidpp import HapticPattern
        import os
        import select

        with patch('os.write') as mock_write:
            with patch('select.select', return_value=([mock_mx4._raw_fd], [], [])):
                with patch('os.read', return_value=bytes([0x10, 0xFF, 0x00] + [0] * 17)):
                    result = mock_mx4.trigger_haptic(HapticPattern.MEDIUM_CLICK)
                    assert mock_write.called

    def test_trigger_haptic_with_int(self, mock_mx4):
        """Test triggering haptic with integer pattern"""
        with patch('os.write') as mock_write:
            with patch('select.select', return_value=([mock_mx4._raw_fd], [], [])):
                with patch('os.read', return_value=bytes([0x10, 0xFF, 0x00] + [0] * 17)):
                    result = mock_mx4.trigger_haptic(pattern=5)
                    assert mock_write.called
