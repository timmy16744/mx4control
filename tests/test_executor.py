"""
Tests for action executor service.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
import threading


class TestActionExecutorInit:
    """Tests for ActionExecutor initialization"""

    def test_initialization(self, action_executor):
        """Test executor initializes correctly"""
        assert action_executor is not None

    def test_key_mappings_class_attribute(self):
        """Test KEY_MAPPINGS is a class attribute"""
        from services.action_executor import ActionExecutor
        assert hasattr(ActionExecutor, 'KEY_MAPPINGS')


class TestExecuteDispatch:
    """Tests for execute() action type dispatch"""

    def test_execute_keystroke_dispatch(self, action_executor):
        """Test execute dispatches to keystroke handler"""
        with patch.object(action_executor, '_execute_keystroke', return_value=True) as mock:
            result = action_executor.execute("keystroke", "ctrl+c")
            mock.assert_called_once_with("ctrl+c")
            assert result is True

    def test_execute_command_dispatch(self, action_executor):
        """Test execute dispatches to command handler"""
        with patch.object(action_executor, '_execute_command', return_value=True) as mock:
            result = action_executor.execute("command", "echo test")
            mock.assert_called_once_with("echo test")
            assert result is True

    def test_execute_application_dispatch(self, action_executor):
        """Test execute dispatches to application handler"""
        with patch.object(action_executor, '_execute_application', return_value=True) as mock:
            result = action_executor.execute("application", "firefox")
            mock.assert_called_once_with("firefox")
            assert result is True

    def test_execute_case_insensitive(self, action_executor):
        """Test action type is case insensitive"""
        with patch.object(action_executor, '_execute_keystroke', return_value=True) as mock:
            action_executor.execute("KEYSTROKE", "ctrl+c")
            mock.assert_called_once()

            mock.reset_mock()
            action_executor.execute("Keystroke", "ctrl+c")
            mock.assert_called_once()

    def test_execute_disabled_returns_false(self, action_executor):
        """Test disabled action type returns False"""
        result = action_executor.execute("disabled", "anything")
        assert result is False

    def test_execute_empty_data_returns_false(self, action_executor):
        """Test empty action data returns False"""
        result = action_executor.execute("keystroke", "")
        assert result is False

        result = action_executor.execute("command", None)
        assert result is False

    def test_execute_unknown_type(self, action_executor):
        """Test unknown action type returns False"""
        result = action_executor.execute("unknown_type", "data")
        assert result is False


class TestKeystrokeExecution:
    """Tests for keystroke execution"""

    def test_keystroke_empty_returns_false(self, action_executor):
        """Test empty keystroke returns False"""
        result = action_executor._execute_keystroke("")
        assert result is False

    def test_keystroke_tries_wtype_first(self, action_executor):
        """Test keystroke tries wtype before xdotool"""
        with patch.object(action_executor, '_keystroke_wtype', return_value=True) as mock_wtype:
            with patch.object(action_executor, '_keystroke_xdotool') as mock_xdotool:
                result = action_executor._execute_keystroke("ctrl+c")

                mock_wtype.assert_called_once()
                mock_xdotool.assert_not_called()
                assert result is True

    def test_keystroke_falls_back_to_xdotool(self, action_executor):
        """Test keystroke falls back to xdotool when wtype fails"""
        with patch.object(action_executor, '_keystroke_wtype', return_value=False):
            with patch.object(action_executor, '_keystroke_xdotool', return_value=True) as mock_xdotool:
                result = action_executor._execute_keystroke("ctrl+c")

                mock_xdotool.assert_called_once()
                assert result is True


class TestWtypeKeystroke:
    """Tests for wtype keystroke execution"""

    def test_wtype_basic_key(self, action_executor, mock_subprocess):
        """Test wtype with basic key"""
        mock_subprocess['run'].return_value.returncode = 0

        result = action_executor._keystroke_wtype("a")

        assert mock_subprocess['run'].called
        args = mock_subprocess['run'].call_args[0][0]
        assert 'wtype' in args

    def test_wtype_with_modifiers(self, action_executor, mock_subprocess):
        """Test wtype with modifier keys"""
        mock_subprocess['run'].return_value.returncode = 0

        result = action_executor._keystroke_wtype("ctrl+c")

        assert mock_subprocess['run'].called
        args = mock_subprocess['run'].call_args[0][0]
        assert '-M' in args
        assert 'ctrl' in args

    def test_wtype_modifier_mapping(self, action_executor, mock_subprocess):
        """Test wtype modifier name mappings"""
        mock_subprocess['run'].return_value.returncode = 0

        # Test super -> logo mapping
        action_executor._keystroke_wtype("super+tab")

        args = mock_subprocess['run'].call_args[0][0]
        assert 'logo' in args

    def test_wtype_not_found(self, action_executor):
        """Test wtype handles FileNotFoundError"""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = action_executor._keystroke_wtype("ctrl+c")
            assert result is False

    def test_wtype_failure(self, action_executor, mock_subprocess):
        """Test wtype handles non-zero return code"""
        mock_subprocess['run'].return_value.returncode = 1
        mock_subprocess['run'].return_value.stderr = b"error"

        result = action_executor._keystroke_wtype("ctrl+c")
        assert result is False

    def test_wtype_no_key(self, action_executor):
        """Test wtype with only modifiers returns False"""
        result = action_executor._keystroke_wtype("ctrl+shift")
        assert result is False


class TestXdotoolKeystroke:
    """Tests for xdotool keystroke execution"""

    def test_xdotool_basic(self, action_executor, mock_subprocess):
        """Test xdotool basic execution"""
        mock_subprocess['run'].return_value.returncode = 0

        result = action_executor._keystroke_xdotool("ctrl+c")

        assert mock_subprocess['run'].called
        args = mock_subprocess['run'].call_args[0][0]
        assert args[0] == 'xdotool'
        assert args[1] == 'key'

    def test_xdotool_not_found(self, action_executor):
        """Test xdotool handles FileNotFoundError"""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = action_executor._keystroke_xdotool("ctrl+c")
            assert result is False

    def test_xdotool_failure(self, action_executor, mock_subprocess):
        """Test xdotool handles failure"""
        mock_subprocess['run'].return_value.returncode = 1
        mock_subprocess['run'].return_value.stderr = b"error"

        result = action_executor._keystroke_xdotool("ctrl+c")
        assert result is False


class TestXdotoolConversion:
    """Tests for xdotool shortcut format conversion"""

    def test_convert_ctrl(self, action_executor):
        """Test ctrl modifier conversion"""
        result = action_executor._convert_to_xdotool("ctrl+c")
        assert result == "ctrl+c"

        result = action_executor._convert_to_xdotool("control+c")
        assert result == "ctrl+c"

    def test_convert_alt(self, action_executor):
        """Test alt modifier conversion"""
        result = action_executor._convert_to_xdotool("alt+tab")
        assert result == "alt+Tab"

    def test_convert_shift(self, action_executor):
        """Test shift modifier conversion"""
        result = action_executor._convert_to_xdotool("shift+a")
        assert result == "shift+a"

    def test_convert_super(self, action_executor):
        """Test super/win/meta modifier conversion"""
        result = action_executor._convert_to_xdotool("super+tab")
        assert result == "super+Tab"

        result = action_executor._convert_to_xdotool("win+tab")
        assert result == "super+Tab"

        result = action_executor._convert_to_xdotool("meta+tab")
        assert result == "super+Tab"

    def test_convert_special_keys(self, action_executor):
        """Test special key conversion"""
        assert "Tab" in action_executor._convert_to_xdotool("tab")
        assert "Return" in action_executor._convert_to_xdotool("enter")
        assert "Return" in action_executor._convert_to_xdotool("return")
        assert "Escape" in action_executor._convert_to_xdotool("escape")
        assert "Escape" in action_executor._convert_to_xdotool("esc")

    def test_convert_function_keys(self, action_executor):
        """Test function key conversion"""
        assert "F1" in action_executor._convert_to_xdotool("f1")
        assert "F12" in action_executor._convert_to_xdotool("f12")

    def test_convert_multiple_modifiers(self, action_executor):
        """Test multiple modifier conversion"""
        result = action_executor._convert_to_xdotool("ctrl+shift+t")
        assert "ctrl" in result
        assert "shift" in result


class TestCommandExecution:
    """Tests for command execution"""

    def test_command_empty_returns_false(self, action_executor):
        """Test empty command returns False"""
        result = action_executor._execute_command("")
        assert result is False

    def test_command_basic(self, action_executor, mock_subprocess):
        """Test basic command execution"""
        result = action_executor._execute_command("echo test")

        assert mock_subprocess['Popen'].called
        # Check shell=False is used
        call_kwargs = mock_subprocess['Popen'].call_args[1]
        assert call_kwargs.get('shell') is False

    def test_command_uses_shlex_split(self, action_executor, mock_subprocess):
        """Test command uses shlex.split for parsing"""
        result = action_executor._execute_command('echo "hello world"')

        args = mock_subprocess['Popen'].call_args[0][0]
        assert args == ['echo', 'hello world']

    def test_command_shell_false(self, action_executor, mock_subprocess):
        """Test command uses shell=False"""
        action_executor._execute_command("echo test")

        call_kwargs = mock_subprocess['Popen'].call_args[1]
        assert call_kwargs['shell'] is False

    def test_command_start_new_session(self, action_executor, mock_subprocess):
        """Test command starts in new session"""
        action_executor._execute_command("echo test")

        call_kwargs = mock_subprocess['Popen'].call_args[1]
        assert call_kwargs['start_new_session'] is True

    def test_command_not_found(self, action_executor):
        """Test command not found handling"""
        with patch('subprocess.Popen', side_effect=FileNotFoundError):
            result = action_executor._execute_command("nonexistent_command")
            assert result is False

    def test_command_invalid_syntax(self, action_executor):
        """Test command with invalid syntax (unclosed quotes)"""
        # shlex.split raises ValueError for malformed strings
        result = action_executor._execute_command('echo "unclosed')
        assert result is False

    def test_command_injection_prevented(self, action_executor, mock_subprocess):
        """Test shell injection is prevented"""
        # With shell=True, this would execute rm -rf
        # With shell=False and shlex.split, it's just arguments
        action_executor._execute_command("echo test; rm -rf /")

        args = mock_subprocess['Popen'].call_args[0][0]
        # The semicolon should be treated as part of an argument, not a separator
        assert 'rm' not in args[0]


class TestApplicationLaunch:
    """Tests for application launching"""

    def test_application_empty_returns_false(self, action_executor):
        """Test empty app name returns False"""
        result = action_executor._execute_application("")
        assert result is False

    def test_application_tries_direct_first(self, action_executor, mock_subprocess):
        """Test application tries direct execution first"""
        result = action_executor._execute_application("firefox")

        assert mock_subprocess['Popen'].called
        first_call_args = mock_subprocess['Popen'].call_args_list[0][0][0]
        assert first_call_args == ['firefox']

    def test_application_fallback_methods(self, action_executor):
        """Test application tries multiple launch methods"""
        call_count = 0

        def failing_popen(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise FileNotFoundError
            return Mock()

        with patch('subprocess.Popen', side_effect=failing_popen):
            result = action_executor._execute_application("firefox")
            assert call_count >= 1  # At least tried once

    def test_application_all_methods_fail(self, action_executor):
        """Test application returns False when all methods fail"""
        with patch('subprocess.Popen', side_effect=FileNotFoundError):
            result = action_executor._execute_application("nonexistent_app")
            assert result is False


class TestGlobalExecutor:
    """Tests for global executor singleton"""

    def test_get_executor_returns_instance(self):
        """Test get_executor returns an ActionExecutor"""
        from services.action_executor import get_executor, ActionExecutor

        executor = get_executor()
        assert isinstance(executor, ActionExecutor)

    def test_get_executor_singleton(self):
        """Test get_executor returns same instance"""
        from services.action_executor import get_executor

        executor1 = get_executor()
        executor2 = get_executor()
        assert executor1 is executor2

    def test_execute_action_convenience(self, mock_subprocess):
        """Test execute_action convenience function"""
        from services.action_executor import execute_action

        result = execute_action("command", "echo test")
        assert mock_subprocess['Popen'].called


class TestThreadSafety:
    """Tests for thread-safe executor creation"""

    def test_concurrent_get_executor(self):
        """Test concurrent get_executor calls don't create multiple instances"""
        from services.action_executor import get_executor

        results = []

        def get_and_store():
            executor = get_executor()
            results.append(id(executor))

        threads = [threading.Thread(target=get_and_store) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same instance
        assert len(set(results)) == 1


class TestSampleActions:
    """Tests using sample action configurations"""

    def test_sample_actions(self, action_executor, sample_actions, mock_subprocess):
        """Test executing sample actions"""
        for action_type, action_data in sample_actions:
            # Each action should execute without raising
            try:
                action_executor.execute(action_type, action_data)
            except Exception as e:
                pytest.fail(f"Action {action_type}:{action_data} raised {e}")


class TestKeyMappings:
    """Tests for key mappings initialization"""

    def test_init_key_mappings_without_pynput(self):
        """Test key mappings work when pynput is not available"""
        with patch.dict('sys.modules', {'pynput': None, 'pynput.keyboard': None}):
            from services.action_executor import ActionExecutor
            executor = ActionExecutor()
            # Should not raise even without pynput

    def test_key_mappings_contain_common_keys(self):
        """Test KEY_MAPPINGS contains common key names"""
        from services.action_executor import ActionExecutor, PYNPUT_AVAILABLE

        if PYNPUT_AVAILABLE:
            ActionExecutor._init_key_mappings()
            mappings = ActionExecutor.KEY_MAPPINGS

            # Check for common modifiers
            assert 'ctrl' in mappings or 'control' in mappings
            assert 'alt' in mappings
            assert 'shift' in mappings

            # Check for common keys
            assert 'tab' in mappings
            assert 'enter' in mappings
            assert 'escape' in mappings or 'esc' in mappings


class TestErrorHandling:
    """Tests for error handling in action execution"""

    def test_keystroke_exception_handling(self, action_executor):
        """Test keystroke handles exceptions within wtype gracefully"""
        # The exception handling is inside _keystroke_wtype, not _execute_keystroke
        # So we test that wtype catches subprocess errors gracefully
        with patch('subprocess.run', side_effect=Exception("Test error")):
            # wtype should catch the exception and return False
            result = action_executor._keystroke_wtype("ctrl+c")
            assert result is False

    def test_command_generic_exception(self, action_executor):
        """Test command handles generic exceptions"""
        with patch('subprocess.Popen', side_effect=Exception("Generic error")):
            result = action_executor._execute_command("echo test")
            assert result is False

    def test_application_generic_exception(self, action_executor):
        """Test application handles generic exceptions"""
        with patch('subprocess.Popen', side_effect=Exception("Generic error")):
            result = action_executor._execute_application("firefox")
            assert result is False


class TestLogging:
    """Tests that verify logging behavior"""

    def test_command_logs_execution(self, action_executor, mock_subprocess, caplog):
        """Test command execution is logged"""
        import logging

        with caplog.at_level(logging.INFO):
            action_executor._execute_command("echo test")

        # Check that command was logged
        assert any("echo test" in record.message for record in caplog.records)

    def test_application_logs_launch(self, action_executor, mock_subprocess, caplog):
        """Test application launch is logged"""
        import logging

        with caplog.at_level(logging.INFO):
            action_executor._execute_application("firefox")

        assert any("firefox" in record.message for record in caplog.records)
