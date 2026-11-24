"""Desktop notification haptic watcher (agent-local).

Watches the session D-Bus for ``org.freedesktop.Notifications.Notify``
method calls via ``dbus-monitor`` when ``haptics.notification_enabled``
is True, pulsing the configured haptic waveform with a debounce cooldown
so notification bursts don't spam the motor.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from typing import Callable, Optional

from ..config.schema import Config

logger = logging.getLogger(__name__)

_COOLDOWN_S = 1.5


class NotificationHapticWatcher:
    """Background watcher that pulses haptics on desktop notifications."""

    def __init__(
        self,
        config_provider: Callable[[], Config],
        trigger_haptic: Callable[[int], bool],
    ) -> None:
        self._config_provider = config_provider
        self._trigger = trigger_haptic
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_fire = 0.0

    def sync(self) -> None:
        """Start or stop watching to match ``config.haptics.notification_enabled``."""
        cfg = self._config_provider()
        want = bool(cfg.haptics.enabled and cfg.haptics.notification_enabled)
        if want and not self._running:
            self.start()
        elif not want and self._running:
            self.stop()

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._proc = subprocess.Popen(
                [
                    "dbus-monitor", "--session",
                    "type='method_call',interface='org.freedesktop.Notifications',member='Notify'",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except OSError as e:
            logger.debug("dbus-monitor unavailable for notification haptics: %s", e)
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="MX4NotifHaptics", daemon=True,
        )
        self._thread.start()
        logger.info("notification haptic watcher started")
        return True

    def stop(self) -> None:
        self._running = False
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                if not self._running:
                    break
                if "member=Notify" in line:
                    now = time.monotonic()
                    if now - self._last_fire < _COOLDOWN_S:
                        continue
                    cfg = self._config_provider()
                    if cfg.haptics.enabled and cfg.haptics.notification_enabled:
                        self._last_fire = now
                        try:
                            self._trigger(cfg.haptics.notification_pattern)
                        except Exception:
                            logger.debug("notification haptic failed", exc_info=True)
        except Exception as e:
            if self._running:
                logger.debug("notification watcher ended: %s", e)
        finally:
            self._running = False
