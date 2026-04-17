"""Unix-socket JSON-RPC server — the daemon's IPC.

Runs on its own thread and calls registered handlers on the GLib main
thread via :func:`GLib.idle_add` so handlers can touch GTK widgets
safely.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
from pathlib import Path
from typing import Callable, Any

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib

from ..common.ipc import default_socket_path, _send_frame, _recv_frame

logger = logging.getLogger(__name__)


Handler = Callable[..., Any]


class IPCServer:
    """Threaded JSON-RPC server.

    Handlers run on whatever thread receives them — wrap with
    :func:`GLib.idle_add` yourself if the operation touches GTK.
    """

    def __init__(self, socket_path: Path | None = None):
        self.socket_path = socket_path or default_socket_path()
        self._handlers: dict[str, Handler] = {}
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        # Remove any stale socket
        try:
            if self.socket_path.exists():
                self.socket_path.unlink()
        except OSError:
            pass
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.socket_path))
        self._sock.listen(16)
        os.chmod(self.socket_path, 0o600)
        self._running = True
        self._thread = threading.Thread(
            target=self._accept_loop, name="MX4IPCServer", daemon=True,
        )
        self._thread.start()
        logger.info(f"IPC listening on {self.socket_path}")

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        try:
            if self.socket_path.exists():
                self.socket_path.unlink()
        except OSError:
            pass

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while self._running:
            try:
                self._sock.settimeout(0.5)
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._handle_connection,
                args=(conn,),
                daemon=True,
                name="MX4IPCConn",
            ).start()

    def _handle_connection(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5.0)
            req = _recv_frame(conn)
            method = req.get("method", "")
            args = req.get("args") or {}
            handler = self._handlers.get(method)

            if handler is None:
                _send_frame(conn, {"ok": False, "error": f"unknown method: {method}"})
                return

            # Dispatch on GLib main thread for safety
            result_holder: dict[str, Any] = {}
            done = threading.Event()

            def run():
                try:
                    result_holder["result"] = handler(**args)
                except Exception as e:
                    logger.exception(f"handler {method} raised")
                    result_holder["error"] = str(e)
                finally:
                    done.set()
                return False  # don't repeat

            GLib.idle_add(run)
            done.wait(timeout=5.0)

            if "error" in result_holder:
                _send_frame(conn, {"ok": False, "error": result_holder["error"]})
            else:
                _send_frame(conn, {"ok": True, "result": result_holder.get("result")})
        except (ConnectionError, OSError, ValueError) as e:
            logger.debug(f"IPC conn error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass
