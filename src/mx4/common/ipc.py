"""Unix-socket JSON-RPC helpers shared by daemon + clients.

Wire format:

    request  := <len:u32-be> <json_bytes>
    response := <len:u32-be> <json_bytes>

Each request is a single-shot JSON object::

    {"method": "get_state", "args": {}}

Each response is::

    {"ok": true, "result": ...}       # success
    {"ok": false, "error": "..."}     # failure

The framing is simple length-prefixed so a client can use
``socket.recv`` in a loop without worrying about boundaries.
"""

from __future__ import annotations

import json
import os
import socket
import struct
from pathlib import Path
from typing import Any


def default_socket_path() -> Path:
    """Standard location — $XDG_RUNTIME_DIR/mx4d.sock."""
    base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(base) / "mx4d.sock"


def _send_frame(sock: socket.socket, obj: Any) -> None:
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("peer closed")
        buf += chunk
    return buf


def _recv_frame(sock: socket.socket) -> Any:
    hdr = _recv_exact(sock, 4)
    (size,) = struct.unpack(">I", hdr)
    if size > 1 << 20:  # 1 MB sanity cap
        raise ValueError(f"frame too large: {size}")
    return json.loads(_recv_exact(sock, size))


# ───────────────────────────── Client ────────────────────────────────────


class DaemonClient:
    """Synchronous JSON-RPC client used by the CLI and the GUI."""

    def __init__(self, socket_path: Path | None = None):
        self.socket_path = socket_path or default_socket_path()

    def call(self, method: str, **args) -> dict:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        try:
            sock.connect(str(self.socket_path))
            _send_frame(sock, {"method": method, "args": args})
            return _recv_frame(sock)
        finally:
            sock.close()

    # Convenience accessors for common calls
    def state(self) -> dict:
        r = self.call("get_state")
        return r.get("result") if r.get("ok") else {"error": r.get("error")}

    def set_dpi(self, dpi: int) -> bool:
        return self.call("set_dpi", dpi=int(dpi)).get("ok", False)

    def set_smartshift(self, enabled: bool, threshold: int = 25) -> bool:
        return self.call("set_smartshift",
                         enabled=bool(enabled),
                         threshold=int(threshold)).get("ok", False)

    def trigger_haptic(self, pattern: int) -> bool:
        return self.call("trigger_haptic", pattern=int(pattern)).get("ok", False)

    def switch_host(self, index: int) -> bool:
        return self.call("switch_host", index=int(index)).get("ok", False)

    def reload(self) -> bool:
        return self.call("reload_config").get("ok", False)

    def is_running(self) -> bool:
        try:
            self.call("ping")
            return True
        except (OSError, ConnectionError):
            return False
