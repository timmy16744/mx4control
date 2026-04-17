"""
Action Executor

Executes actions triggered by gesture selections, including
keystrokes, application launches, and shell commands.
"""

import subprocess
import logging
import shlex
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import pynput for keystroke simulation
# Fall back to xdotool if not available
try:
    from pynput.keyboard import Key, Controller as KeyboardController
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    Key = None
    KeyboardController = None
    logger.debug("pynput not available, will use xdotool for keystrokes")


class ActionExecutor:
    """
    Executes various action types triggered by the Actions Ring.

    Supports:
    - keystroke: Keyboard shortcuts (e.g., "ctrl+c", "super+tab")
    - command: Shell commands (e.g., "gnome-screenshot -a")
    - application: Launch applications by name
    """

    # Key name mappings for pynput (populated at runtime if available)
    KEY_MAPPINGS = {}

    @classmethod
    def _init_key_mappings(cls):
        """Initialize key mappings if pynput is available"""
        if PYNPUT_AVAILABLE and Key is not None and not cls.KEY_MAPPINGS:
            cls.KEY_MAPPINGS = {
                'ctrl': Key.ctrl,
                'control': Key.ctrl,
                'alt': Key.alt,
                'shift': Key.shift,
                'super': Key.cmd,
                'win': Key.cmd,
                'meta': Key.cmd,
                'tab': Key.tab,
                'enter': Key.enter,
                'return': Key.enter,
                'space': Key.space,
                'backspace': Key.backspace,
                'delete': Key.delete,
                'escape': Key.esc,
                'esc': Key.esc,
                'home': Key.home,
                'end': Key.end,
                'pageup': Key.page_up,
                'pagedown': Key.page_down,
                'up': Key.up,
                'down': Key.down,
                'left': Key.left,
                'right': Key.right,
                'f1': Key.f1,
                'f2': Key.f2,
                'f3': Key.f3,
                'f4': Key.f4,
                'f5': Key.f5,
                'f6': Key.f6,
                'f7': Key.f7,
                'f8': Key.f8,
                'f9': Key.f9,
                'f10': Key.f10,
                'f11': Key.f11,
                'f12': Key.f12,
            }

    def __init__(self):
        self._init_key_mappings()
        self._keyboard = None
        if PYNPUT_AVAILABLE:
            try:
                self._keyboard = KeyboardController()
            except Exception as e:
                logger.warning(f"Failed to initialize pynput keyboard: {e}")

    def execute(self, action_type: str, action_data: str) -> bool:
        """
        Execute an action.

        Args:
            action_type: Type of action (keystroke, command, application, disabled)
            action_data: Action-specific data (shortcut string, command, app name)

        Returns:
            True if successful
        """
        if not action_data or action_type == "disabled":
            return False

        action_type = action_type.lower()

        if action_type == "keystroke":
            return self._execute_keystroke(action_data)
        elif action_type == "command":
            return self._execute_command(action_data)
        elif action_type == "application":
            return self._execute_application(action_data)
        else:
            logger.warning(f"Unknown action type: {action_type}")
            return False

    def _execute_keystroke(self, shortcut: str) -> bool:
        """
        Execute a keyboard shortcut.

        Args:
            shortcut: Shortcut string like "ctrl+c", "super+tab", "ctrl+shift+t"

        Returns:
            True if successful
        """
        if not shortcut:
            return False

        logger.info(f"Executing keystroke: {shortcut}")

        # Try wtype first (Wayland-native, most reliable)
        if self._keystroke_wtype(shortcut):
            return True

        # Fall back to xdotool (works on X11/XWayland)
        return self._keystroke_xdotool(shortcut)

    def _keystroke_wtype(self, shortcut: str) -> bool:
        """Execute keystroke using wtype (Wayland-native)"""
        try:
            # Convert shortcut to wtype format
            # wtype uses -M for modifiers, -m to release, -k for keys
            parts = [p.strip().lower() for p in shortcut.replace('+', ' ').split()]

            # Map modifier names to wtype modifier names
            modifier_map = {
                'ctrl': 'ctrl', 'control': 'ctrl',
                'alt': 'alt',
                'shift': 'shift',
                'super': 'logo', 'win': 'logo', 'meta': 'logo',
            }

            modifiers = []
            key = None

            for part in parts:
                if part in modifier_map:
                    modifiers.append(modifier_map[part])
                else:
                    key = part

            if not key:
                logger.debug(f"wtype: no key found in '{shortcut}'")
                return False

            # Build wtype command
            cmd = ['wtype']
            for mod in modifiers:
                cmd.extend(['-M', mod])
            cmd.extend(['-k', key])
            for mod in reversed(modifiers):
                cmd.extend(['-m', mod])

            logger.debug(f"Running wtype: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, timeout=2)

            if result.returncode == 0:
                logger.debug(f"wtype executed successfully: {' '.join(cmd)}")
                return True
            else:
                logger.debug(f"wtype failed: {result.stderr.decode()}")
                return False

        except FileNotFoundError:
            logger.debug("wtype not found")
            return False
        except Exception as e:
            logger.debug(f"wtype error: {e}")
            return False

    def _keystroke_pynput(self, parts: list[str]) -> bool:
        """Execute keystroke using pynput"""
        try:
            modifiers = []
            key = None

            for part in parts:
                if part in self.KEY_MAPPINGS:
                    key_obj = self.KEY_MAPPINGS[part]
                    # Check if it's a modifier
                    if key_obj in [Key.ctrl, Key.alt, Key.shift, Key.cmd]:
                        modifiers.append(key_obj)
                    else:
                        key = key_obj
                elif len(part) == 1:
                    key = part
                else:
                    # Try as a special key name
                    mapped = self.KEY_MAPPINGS.get(part)
                    if mapped:
                        key = mapped
                    else:
                        key = part

            if key is None and modifiers:
                # Just modifiers, no key
                return False

            # Press modifiers
            for mod in modifiers:
                self._keyboard.press(mod)

            # Press and release the main key
            if key:
                self._keyboard.press(key)
                self._keyboard.release(key)

            # Release modifiers (in reverse order)
            for mod in reversed(modifiers):
                self._keyboard.release(mod)

            return True

        except Exception as e:
            logger.error(f"pynput keystroke failed: {e}")
            # Fall back to xdotool
            return self._keystroke_xdotool('+'.join(parts))

    def _keystroke_xdotool(self, shortcut: str) -> bool:
        """Execute keystroke using xdotool"""
        try:
            # Convert shortcut format to xdotool format
            # e.g., "ctrl+c" -> "ctrl+c", "super+tab" -> "super+Tab"
            xdotool_shortcut = self._convert_to_xdotool(shortcut)

            result = subprocess.run(
                ['xdotool', 'key', xdotool_shortcut],
                capture_output=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.error(f"xdotool failed: {result.stderr.decode()}")
                return False

            return True

        except FileNotFoundError:
            logger.error("xdotool not found. Install with: sudo pacman -S xdotool")
            return False
        except Exception as e:
            logger.error(f"xdotool keystroke failed: {e}")
            return False

    def _convert_to_xdotool(self, shortcut: str) -> str:
        """Convert shortcut string to xdotool format"""
        parts = shortcut.lower().replace(' ', '+').split('+')
        converted = []

        for part in parts:
            part = part.strip()
            if part in ['ctrl', 'control']:
                converted.append('ctrl')
            elif part in ['alt']:
                converted.append('alt')
            elif part in ['shift']:
                converted.append('shift')
            elif part in ['super', 'win', 'meta']:
                converted.append('super')
            elif part == 'tab':
                converted.append('Tab')
            elif part == 'enter' or part == 'return':
                converted.append('Return')
            elif part == 'space':
                converted.append('space')
            elif part == 'escape' or part == 'esc':
                converted.append('Escape')
            elif part.startswith('f') and part[1:].isdigit():
                converted.append(part.upper())  # F1, F2, etc.
            elif len(part) == 1:
                converted.append(part)
            else:
                converted.append(part)

        return '+'.join(converted)

    def _execute_command(self, command: str) -> bool:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute

        Returns:
            True if successfully launched
        """
        if not command:
            return False

        logger.info(f"Executing command: {command}")

        try:
            # Parse command safely using shlex to prevent shell injection
            # This splits the command respecting quotes and escapes
            args = shlex.split(command)

            if not args:
                logger.error("Empty command after parsing")
                return False

            # Use subprocess.Popen with shell=False for security
            subprocess.Popen(
                args,
                shell=False,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True

        except ValueError as e:
            # shlex.split raises ValueError for malformed strings (unclosed quotes)
            logger.error(f"Invalid command syntax: {e}")
            return False
        except FileNotFoundError:
            logger.error(f"Command not found: {command.split()[0] if command else 'unknown'}")
            return False
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return False

    def _execute_application(self, app_name: str) -> bool:
        """
        Launch an application by name.

        Args:
            app_name: Application name or .desktop file name

        Returns:
            True if successfully launched
        """
        if not app_name:
            return False

        logger.info(f"Launching application: {app_name}")

        # Try different methods to launch the application
        methods = [
            # Direct execution
            lambda: subprocess.Popen(
                [app_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
            # Via gtk-launch (for .desktop files)
            lambda: subprocess.Popen(
                ['gtk-launch', app_name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
            # Via gio (GNOME method)
            lambda: subprocess.Popen(
                ['gio', 'launch', f'{app_name}.desktop'],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ),
        ]

        for method in methods:
            try:
                method()
                return True
            except Exception:
                continue

        logger.error(f"Failed to launch application: {app_name}")
        return False


# Global executor instance with thread-safe initialization
_executor: Optional[ActionExecutor] = None
_executor_lock = threading.Lock()


def get_executor() -> ActionExecutor:
    """Get or create the global action executor (thread-safe)"""
    global _executor
    if _executor is None:
        with _executor_lock:
            # Double-check after acquiring lock
            if _executor is None:
                _executor = ActionExecutor()
    return _executor


def execute_action(action_type: str, action_data: str) -> bool:
    """Convenience function to execute an action"""
    return get_executor().execute(action_type, action_data)
