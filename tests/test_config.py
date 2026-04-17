"""
Tests for configuration management.
"""

import pytest
import json
from pathlib import Path


class TestConfigManager:
    """Tests for ConfigManager class"""

    def test_default_config_creation(self, config_manager):
        """Test that default config is created when no file exists"""
        config = config_manager.config

        assert config is not None
        assert config.version == 1
        assert config.theme == "dark"
        assert config.haptics.intensity == 2
        assert config.pointer.dpi == 1000

    def test_save_and_load_config(self, config_manager):
        """Test saving and loading configuration"""
        # Modify config
        config_manager.config.theme = "light"
        config_manager.config.haptics.intensity = 3
        config_manager.config.pointer.dpi = 1600

        # Save
        assert config_manager.save() is True

        # Create new manager to test loading
        from core.config import ConfigManager
        new_manager = ConfigManager(config_path=config_manager.config_path)
        loaded_config = new_manager.load()

        assert loaded_config.theme == "light"
        assert loaded_config.haptics.intensity == 3
        assert loaded_config.pointer.dpi == 1600

    def test_load_existing_config(self, temp_config_dir, sample_config):
        """Test loading an existing config file"""
        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(sample_config, f)

        from core.config import ConfigManager
        manager = ConfigManager(config_path=config_path)
        config = manager.load()

        assert config.theme == "dark"
        assert config.haptics.intensity == 2
        assert config.pointer.dpi == 1600
        assert len(config.buttons) == 3

    def test_config_reset(self, config_manager):
        """Test resetting config to defaults"""
        # Modify config
        config_manager.config.theme = "light"
        config_manager.config.haptics.intensity = 0

        # Reset
        config_manager.reset()

        assert config_manager.config.theme == "dark"
        assert config_manager.config.haptics.intensity == 2

    def test_invalid_config_file_fallback(self, temp_config_dir):
        """Test fallback to defaults when config file is invalid"""
        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            f.write("invalid json {{{")

        from core.config import ConfigManager
        manager = ConfigManager(config_path=config_path)
        config = manager.load()

        # Should fall back to defaults
        assert config.version == 1
        assert config.theme == "dark"

    def test_partial_config_loading(self, temp_config_dir):
        """Test loading config with missing fields uses defaults"""
        partial_config = {
            "version": 1,
            "theme": "light",
            # Missing haptics, pointer, etc.
        }
        config_path = temp_config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(partial_config, f)

        from core.config import ConfigManager
        manager = ConfigManager(config_path=config_path)
        config = manager.load()

        assert config.theme == "light"
        # Defaults should be used for missing fields
        assert config.haptics.intensity == 2
        assert config.pointer.dpi == 1000


class TestHapticSettings:
    """Tests for HapticSettings dataclass"""

    def test_default_values(self):
        """Test default haptic settings"""
        from core.config import HapticSettings

        settings = HapticSettings()

        assert settings.enabled is True
        assert settings.intensity == 2
        assert settings.selected_pattern == 2
        assert settings.notification_enabled is True
        assert settings.scroll_end_enabled is False
        assert settings.device_switch_enabled is True

    def test_custom_values(self):
        """Test custom haptic settings"""
        from core.config import HapticSettings

        settings = HapticSettings(
            enabled=False,
            intensity=3,
            selected_pattern=5,
            notification_enabled=False,
        )

        assert settings.enabled is False
        assert settings.intensity == 3
        assert settings.selected_pattern == 5
        assert settings.notification_enabled is False


class TestPointerSettings:
    """Tests for PointerSettings dataclass"""

    def test_default_values(self):
        """Test default pointer settings"""
        from core.config import PointerSettings

        settings = PointerSettings()

        assert settings.dpi == 1000
        assert settings.angle_snapping is False
        assert settings.acceleration == 0.0

    def test_dpi_range(self):
        """Test DPI can be set to various values"""
        from core.config import PointerSettings

        for dpi in [400, 800, 1000, 1600, 2000, 4000, 8000]:
            settings = PointerSettings(dpi=dpi)
            assert settings.dpi == dpi


class TestScrollSettings:
    """Tests for ScrollSettings dataclass"""

    def test_default_values(self):
        """Test default scroll settings"""
        from core.config import ScrollSettings

        settings = ScrollSettings()

        assert settings.smartshift_enabled is True
        assert settings.smartshift_threshold == 25
        assert settings.hires_enabled is True
        assert settings.invert_vertical is False
        assert settings.invert_horizontal is False


class TestButtonMapping:
    """Tests for ButtonMapping dataclass"""

    def test_default_values(self):
        """Test default button mapping"""
        from core.config import ButtonMapping

        mapping = ButtonMapping(button_id=0)

        assert mapping.button_id == 0
        assert mapping.action_type == "default"
        assert mapping.action_data == ""

    def test_custom_mapping(self):
        """Test custom button mapping"""
        from core.config import ButtonMapping

        mapping = ButtonMapping(
            button_id=3,
            action_type="keystroke",
            action_data="ctrl+c",
        )

        assert mapping.button_id == 3
        assert mapping.action_type == "keystroke"
        assert mapping.action_data == "ctrl+c"


class TestActionsRingSlice:
    """Tests for ActionsRingSlice dataclass"""

    def test_default_values(self):
        """Test default actions ring slice"""
        from core.config import ActionsRingSlice

        slice = ActionsRingSlice(position=0)

        assert slice.position == 0
        assert slice.label == ""
        assert slice.icon == ""
        assert slice.action_type == "keystroke"
        assert slice.action_data == ""

    def test_custom_slice(self):
        """Test custom actions ring slice"""
        from core.config import ActionsRingSlice

        slice = ActionsRingSlice(
            position=0,
            label="Copy",
            icon="edit-copy",
            action_type="keystroke",
            action_data="ctrl+c",
        )

        assert slice.label == "Copy"
        assert slice.icon == "edit-copy"
        assert slice.action_data == "ctrl+c"
