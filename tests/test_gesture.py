"""
Tests for gesture detection service.
"""

import pytest
import math
from unittest.mock import Mock, patch, MagicMock
import threading
import time


class TestGestureDirection:
    """Tests for GestureDirection enum"""

    def test_direction_values_exist(self):
        """Test that all expected directions exist"""
        from services.gesture_detector import GestureDirection

        assert hasattr(GestureDirection, 'NONE')
        assert hasattr(GestureDirection, 'UP')
        assert hasattr(GestureDirection, 'DOWN')
        assert hasattr(GestureDirection, 'LEFT')
        assert hasattr(GestureDirection, 'RIGHT')
        assert hasattr(GestureDirection, 'CENTER')

    def test_directions_are_unique(self):
        """Test that all directions have unique values"""
        from services.gesture_detector import GestureDirection

        values = [d.value for d in GestureDirection]
        assert len(values) == len(set(values))


class TestGestureEvent:
    """Tests for GestureEvent dataclass"""

    def test_event_creation(self):
        """Test creating a gesture event"""
        from services.gesture_detector import GestureEvent, GestureDirection

        event = GestureEvent(
            direction=GestureDirection.UP,
            start_time=1000.0,
            end_time=1000.5,
            distance=150.0,
            dx=0,
            dy=-150,
        )

        assert event.direction == GestureDirection.UP
        assert event.end_time - event.start_time == 0.5
        assert event.distance == 150.0
        assert event.dx == 0
        assert event.dy == -150

    def test_event_duration(self):
        """Test calculating event duration"""
        from services.gesture_detector import GestureEvent, GestureDirection

        event = GestureEvent(
            direction=GestureDirection.LEFT,
            start_time=100.0,
            end_time=102.5,
            distance=200.0,
            dx=-200,
            dy=0,
        )

        duration = event.end_time - event.start_time
        assert duration == 2.5


class TestGestureDetectorInit:
    """Tests for GestureDetector initialization"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_initial_state(self, detector):
        """Test detector initial state"""
        assert detector._gesture_active is False
        assert detector._running is False
        assert detector._accumulated_dx == 0
        assert detector._accumulated_dy == 0
        assert detector._device_grabbed is False

    def test_callbacks_initially_none(self, detector):
        """Test callbacks are None initially"""
        assert detector.on_gesture_start is None
        assert detector.on_gesture_move is None
        assert detector.on_gesture_end is None

    def test_thresholds(self, detector):
        """Test threshold values are reasonable"""
        assert detector.DIRECTION_THRESHOLD > 0
        assert detector.CENTER_DEADZONE > 0
        assert detector.CENTER_DEADZONE <= detector.DIRECTION_THRESHOLD


class TestDirectionCalculation:
    """Tests for direction calculation logic"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_center_no_movement(self, detector):
        """Test center is returned for no movement"""
        from services.gesture_detector import GestureDirection

        direction = detector._calculate_direction(0, 0)
        assert direction == GestureDirection.CENTER

    def test_center_within_deadzone(self, detector):
        """Test center is returned for movement within deadzone"""
        from services.gesture_detector import GestureDirection

        # Movement within deadzone
        direction = detector._calculate_direction(5, 5)
        assert direction == GestureDirection.CENTER

    def test_direction_right(self, detector):
        """Test right direction detection"""
        from services.gesture_detector import GestureDirection

        # Large movement to the right
        direction = detector._calculate_direction(100, 0)
        assert direction == GestureDirection.RIGHT

        # Slight angle still right
        direction = detector._calculate_direction(100, 30)
        assert direction == GestureDirection.RIGHT

    def test_direction_left(self, detector):
        """Test left direction detection"""
        from services.gesture_detector import GestureDirection

        direction = detector._calculate_direction(-100, 0)
        assert direction == GestureDirection.LEFT

        direction = detector._calculate_direction(-100, -30)
        assert direction == GestureDirection.LEFT

    def test_direction_up(self, detector):
        """Test up direction detection (negative Y)"""
        from services.gesture_detector import GestureDirection

        direction = detector._calculate_direction(0, -100)
        assert direction == GestureDirection.UP

        direction = detector._calculate_direction(30, -100)
        assert direction == GestureDirection.UP

    def test_direction_down(self, detector):
        """Test down direction detection (positive Y)"""
        from services.gesture_detector import GestureDirection

        direction = detector._calculate_direction(0, 100)
        assert direction == GestureDirection.DOWN

        direction = detector._calculate_direction(-30, 100)
        assert direction == GestureDirection.DOWN

    def test_diagonal_up_right(self, detector):
        """Test diagonal up-right (45 degrees)"""
        from services.gesture_detector import GestureDirection

        # At exactly 45 degrees up-right, should be UP or RIGHT
        # The boundary is at -45 degrees, so (100, -100) should be UP
        direction = detector._calculate_direction(100, -100)
        # 45 degree angle in negative Y quadrant
        # atan2(-100, 100) = -45 degrees, which is on the boundary
        assert direction in (GestureDirection.UP, GestureDirection.RIGHT)

    def test_diagonal_down_left(self, detector):
        """Test diagonal down-left"""
        from services.gesture_detector import GestureDirection

        direction = detector._calculate_direction(-100, 100)
        # atan2(100, -100) = 135 degrees, boundary between DOWN and LEFT
        assert direction in (GestureDirection.DOWN, GestureDirection.LEFT)

    def test_just_above_threshold(self, detector):
        """Test movement just above direction threshold"""
        from services.gesture_detector import GestureDirection

        # Just above threshold to the right
        threshold = detector.DIRECTION_THRESHOLD
        direction = detector._calculate_direction(threshold + 1, 0)
        assert direction == GestureDirection.RIGHT

    def test_just_below_threshold(self, detector):
        """Test movement just below direction threshold"""
        from services.gesture_detector import GestureDirection

        # Just below threshold
        threshold = detector.DIRECTION_THRESHOLD
        distance = threshold - 1
        direction = detector._calculate_direction(distance, 0)
        assert direction == GestureDirection.CENTER


class TestGestureStateManagement:
    """Tests for gesture start/end state management"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_start_gesture(self, detector):
        """Test starting a gesture"""
        detector._start_gesture()

        assert detector._gesture_active is True
        assert detector._gesture_start_time > 0
        assert detector._accumulated_dx == 0
        assert detector._accumulated_dy == 0

    def test_start_gesture_resets_accumulation(self, detector):
        """Test that starting a gesture resets accumulated movement"""
        # Simulate some accumulated movement
        detector._accumulated_dx = 100
        detector._accumulated_dy = -50

        detector._start_gesture()

        assert detector._accumulated_dx == 0
        assert detector._accumulated_dy == 0

    def test_start_gesture_callback(self, detector):
        """Test that start callback is called"""
        callback = Mock()
        detector.on_gesture_start = callback

        detector._start_gesture()

        callback.assert_called_once()

    def test_start_gesture_already_active(self, detector):
        """Test starting gesture when already active does nothing"""
        callback = Mock()
        detector.on_gesture_start = callback

        detector._start_gesture()
        detector._start_gesture()  # Second call should be ignored

        callback.assert_called_once()

    def test_end_gesture(self, detector):
        """Test ending a gesture"""
        from services.gesture_detector import GestureDirection

        detector._start_gesture()
        detector._accumulated_dx = 100
        detector._accumulated_dy = 0

        detector._end_gesture()

        assert detector._gesture_active is False

    def test_end_gesture_callback(self, detector):
        """Test that end callback is called with event"""
        from services.gesture_detector import GestureEvent, GestureDirection

        callback = Mock()
        detector.on_gesture_end = callback

        detector._start_gesture()
        detector._accumulated_dx = 100
        detector._accumulated_dy = 0
        detector._end_gesture()

        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert isinstance(event, GestureEvent)
        assert event.direction == GestureDirection.RIGHT
        assert event.dx == 100
        assert event.dy == 0

    def test_end_gesture_not_active(self, detector):
        """Test ending gesture when not active does nothing"""
        callback = Mock()
        detector.on_gesture_end = callback

        detector._end_gesture()

        callback.assert_not_called()

    def test_gesture_distance_calculation(self, detector):
        """Test gesture distance is calculated correctly"""
        callback = Mock()
        detector.on_gesture_end = callback

        detector._start_gesture()
        detector._accumulated_dx = 30
        detector._accumulated_dy = 40
        detector._end_gesture()

        event = callback.call_args[0][0]
        assert event.distance == 50.0  # 3-4-5 triangle

    def test_callback_exception_handled(self, detector):
        """Test that callback exceptions are handled gracefully"""
        def failing_callback():
            raise ValueError("Test error")

        detector.on_gesture_start = failing_callback

        # Should not raise
        detector._start_gesture()
        assert detector._gesture_active is True


class TestMovementHandling:
    """Tests for mouse movement handling"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        mock_ecodes = Mock()
        mock_ecodes.REL_X = 0
        mock_ecodes.REL_Y = 1

        with patch.dict('sys.modules', {'evdev': Mock(), 'evdev.ecodes': mock_ecodes}):
            from services.gesture_detector import GestureDetector
            det = GestureDetector()
            # Patch ecodes on the detector
            return det

    def test_movement_accumulation(self, detector):
        """Test that movement is accumulated correctly"""
        mock_event = Mock()
        mock_event.type = 2  # EV_REL
        mock_event.code = 0  # REL_X
        mock_event.value = 10

        with patch('services.gesture_detector.ecodes') as mock_ecodes:
            mock_ecodes.REL_X = 0
            mock_ecodes.REL_Y = 1

            detector._start_gesture()

            mock_event.code = 0  # REL_X
            mock_event.value = 10
            detector._handle_movement(mock_event)

            assert detector._accumulated_dx == 10

    def test_movement_when_not_active(self, detector):
        """Test that movement is ignored when gesture not active"""
        mock_event = Mock()
        mock_event.code = 0
        mock_event.value = 100

        with patch('services.gesture_detector.ecodes') as mock_ecodes:
            mock_ecodes.REL_X = 0
            mock_ecodes.REL_Y = 1

            # Don't start gesture
            detector._handle_movement(mock_event)

            assert detector._accumulated_dx == 0

    def test_move_callback_called(self, detector):
        """Test that move callback is called during gesture"""
        from services.gesture_detector import GestureDirection

        callback = Mock()
        detector.on_gesture_move = callback

        mock_event = Mock()
        mock_event.code = 0  # REL_X
        mock_event.value = 100

        with patch('services.gesture_detector.ecodes') as mock_ecodes:
            mock_ecodes.REL_X = 0
            mock_ecodes.REL_Y = 1

            detector._start_gesture()
            detector._handle_movement(mock_event)

            callback.assert_called()


class TestThreadSafety:
    """Tests for thread safety of gesture detector"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_gesture_lock_exists(self, detector):
        """Test that gesture lock is created"""
        assert hasattr(detector, '_gesture_lock')
        assert isinstance(detector._gesture_lock, type(threading.Lock()))

    def test_concurrent_start_end(self, detector):
        """Test concurrent start/end calls don't corrupt state"""
        results = []

        def start_then_end():
            for _ in range(10):
                detector._start_gesture()
                time.sleep(0.001)
                detector._end_gesture()
            results.append(True)

        threads = [threading.Thread(target=start_then_end) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads completed
        assert len(results) == 5
        # State is consistent (not active after all threads done)
        assert detector._gesture_active is False


class TestDeviceGrab:
    """Tests for device grab functionality"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance with mock evdev device"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            det = GestureDetector()
            det._evdev_device = Mock()
            det._evdev_device.grab = Mock()
            det._evdev_device.ungrab = Mock()
            return det

    def test_grab_on_button_press(self, detector):
        """Test device is grabbed on gesture button press"""
        mock_event = Mock()
        mock_event.code = 275  # BTN_SIDE
        mock_event.value = 1  # Press

        with patch('services.gesture_detector.ecodes') as mock_ecodes:
            mock_ecodes.BTN_SIDE = 275
            mock_ecodes.BTN_EXTRA = 276

            detector._handle_evdev_button_with_grab(mock_event)

            detector._evdev_device.grab.assert_called_once()
            assert detector._device_grabbed is True

    def test_ungrab_on_button_release(self, detector):
        """Test device is ungrabbed on gesture button release"""
        mock_event = Mock()
        mock_event.code = 275  # BTN_SIDE
        mock_event.value = 0  # Release

        detector._device_grabbed = True  # Simulate grabbed state

        with patch('services.gesture_detector.ecodes') as mock_ecodes:
            mock_ecodes.BTN_SIDE = 275
            mock_ecodes.BTN_EXTRA = 276

            detector._handle_evdev_button_with_grab(mock_event)

            detector._evdev_device.ungrab.assert_called_once()
            assert detector._device_grabbed is False

    def test_non_gesture_button_ignored(self, detector):
        """Test non-gesture buttons don't trigger grab"""
        mock_event = Mock()
        mock_event.code = 272  # BTN_LEFT (not a gesture button)
        mock_event.value = 1

        with patch('services.gesture_detector.ecodes') as mock_ecodes:
            mock_ecodes.BTN_SIDE = 275
            mock_ecodes.BTN_EXTRA = 276

            detector._handle_evdev_button_with_grab(mock_event)

            detector._evdev_device.grab.assert_not_called()


class TestGestureDirectionComprehensive:
    """Comprehensive tests for all direction angles"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_cardinal_directions(self, detector, gesture_directions):
        """Test cardinal direction detection using fixture"""
        for dx, dy, expected_name in gesture_directions:
            result = detector._calculate_direction(dx, dy)
            # Compare by name to avoid enum identity issues across imports
            assert result.name == expected_name, f"Expected {expected_name} for ({dx}, {dy}), got {result.name}"

    def test_all_angles_covered(self, detector):
        """Test that all angles map to a valid direction"""
        from services.gesture_detector import GestureDirection

        # Test angles from 0 to 360 in 10-degree increments
        radius = 100  # Well above threshold
        for angle_deg in range(0, 360, 10):
            angle_rad = math.radians(angle_deg)
            dx = int(radius * math.cos(angle_rad))
            dy = int(radius * math.sin(angle_rad))

            direction = detector._calculate_direction(dx, dy)
            assert direction != GestureDirection.NONE
            assert direction != GestureDirection.CENTER  # Should have a direction

    def test_sector_boundaries(self, detector):
        """Test directions at sector boundaries"""
        from services.gesture_detector import GestureDirection

        # At 45 degrees (boundary between RIGHT and DOWN)
        # cos(45) ≈ 0.707, sin(45) ≈ 0.707
        dx = 71
        dy = 71
        direction = detector._calculate_direction(dx, dy)
        assert direction in (GestureDirection.RIGHT, GestureDirection.DOWN)

        # At 135 degrees (boundary between DOWN and LEFT)
        dx = -71
        dy = 71
        direction = detector._calculate_direction(dx, dy)
        assert direction in (GestureDirection.DOWN, GestureDirection.LEFT)

        # At 225 degrees (boundary between LEFT and UP)
        dx = -71
        dy = -71
        direction = detector._calculate_direction(dx, dy)
        assert direction in (GestureDirection.LEFT, GestureDirection.UP)

        # At 315 degrees (boundary between UP and RIGHT)
        dx = 71
        dy = -71
        direction = detector._calculate_direction(dx, dy)
        assert direction in (GestureDirection.UP, GestureDirection.RIGHT)


class TestIsRunning:
    """Tests for running state"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_is_running_initially_false(self, detector):
        """Test is_running is false initially"""
        assert detector.is_running is False

    def test_is_running_property(self, detector):
        """Test is_running reflects internal state"""
        detector._running = True
        assert detector.is_running is True

        detector._running = False
        assert detector.is_running is False


class TestDeviceName:
    """Tests for device name property"""

    @pytest.fixture
    def detector(self):
        """Create a GestureDetector instance"""
        with patch.dict('sys.modules', {'evdev': Mock()}):
            from services.gesture_detector import GestureDetector
            return GestureDetector()

    def test_device_name_none_when_no_device(self, detector):
        """Test device_name is None when no device connected"""
        assert detector.device_name is None

    def test_device_name_returns_evdev_name(self, detector):
        """Test device_name returns the evdev device name"""
        mock_device = Mock()
        mock_device.name = "Logitech MX Master 4"
        detector._evdev_device = mock_device

        assert detector.device_name == "Logitech MX Master 4"
