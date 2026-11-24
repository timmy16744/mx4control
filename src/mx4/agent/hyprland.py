"""Persistent listener for the Hyprland events socket.

Hyprland exposes an append-only text socket at
``$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock``.
Messages are newline-terminated ``<event>>>data`` lines. We subscribe
once and keep the socket open forever; every ``activewindow`` message
updates the cached focused class. The Actions Ring profile manager
reads the cache with zero syscalls per gesture — replacing the
previous ``subprocess.run(['hyprctl', ...])`` polling.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _socket_path() -> Optional[Path]:
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not signature or not runtime:
        return None
    p = Path(runtime) / "hypr" / signature / ".socket2.sock"
    return p if p.exists() else None


class HyprlandFocusWatcher:
    """Subscribe to Hyprland ``activewindow`` events."""

    def __init__(self, on_change: Callable[[str, str], None]):
        """
        Args:
            on_change: ``(app_class, title) -> None``. Called on the
                listener thread for every activewindow event.
        """
        self._on_change = on_change
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._current_class = ""
        self._current_title = ""
        self._lock = threading.Lock()

    @property
    def current(self) -> tuple[str, str]:
        with self._lock:
            return self._current_class, self._current_title

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        path = _socket_path()
        if not path:
            logger.info("Hyprland socket not available; focus detection disabled")
            return False
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="HyprlandWatcher",
            args=(path,), daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False

    def _loop(self, path: Path) -> None:
        while self._running:
            try:
                self._subscribe_once(path)
            except Exception as e:
                logger.debug(f"hyprland listener error: {e}; reconnecting")
            time.sleep(1.0)

    def _subscribe_once(self, path: Path) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect(str(path))
            buf = b""
            while self._running:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    return  # socket closed, outer loop reconnects
                buf += chunk
                while b"\n" in buf:
                    line, _, buf = buf.partition(b"\n")
                    self._dispatch(line.decode("utf-8", errors="ignore"))
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _dispatch(self, line: str) -> None:
        if not line:
            return
        event, _, data = line.partition(">>")
        if event == "activewindow":
            # Format: "class,title"  (title may contain commas)
            app_class, _, title = data.partition(",")
            with self._lock:
                self._current_class = app_class.lower().strip()
                self._current_title = title.strip()
            try:
                self._on_change(self._current_class, self._current_title)
            except Exception as e:
                logger.exception(f"focus handler raised: {e}")
