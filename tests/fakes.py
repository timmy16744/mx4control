"""A fake HID++ dispatcher that replays captured fixture responses.

Lets us test the ``MXMaster4`` parsers (and write paths) with no hardware
and no root. Response keys match the fixture format
``0x{feat:04x}.{fn:02x}({arg, arg, ...})`` with lowercase hex bytes; a
``0x{feat:04x}.{fn:02x}(*)`` wildcard entry matches any args for that
function (handy for asserting setter calls without pinning exact bytes).
"""

from __future__ import annotations

from typing import Optional

from mx4.hidpp.features import HIDPPError


def hexbytes(s: str) -> bytes:
    return bytes(int(b, 16) for b in s.split())


class FakeDispatcher:
    def __init__(self, feature_cache: dict[int, int],
                 responses: dict[str, str], missing: Optional[bytes] = None):
        self._feature_cache = {int(k): v for k, v in feature_cache.items()}
        self._responses = dict(responses)
        self._missing = missing
        self.calls: list[tuple[int, int, tuple[int, ...]]] = []
        self.writes: list[tuple[int, int, tuple[int, ...]]] = []

    # ─── lifecycle no-ops ───
    def open(self) -> bool:
        return True

    def close(self) -> None:
        pass

    @property
    def is_open(self) -> bool:
        return True

    # ─── feature lookup ───
    def has_feature(self, feature_id: int) -> bool:
        return int(feature_id) in self._feature_cache

    def feature_index(self, feature_id: int) -> Optional[int]:
        return self._feature_cache.get(int(feature_id))

    @property
    def feature_cache(self) -> dict[int, int]:
        return dict(self._feature_cache)

    # ─── request / write ───
    def _key(self, feat: int, fn: int, args: tuple[int, ...]) -> str:
        argstr = ", ".join(f"{a & 0xFF:02x}" for a in args)
        return f"0x{int(feat):04x}.{fn:02x}({argstr})"

    def request(self, feature_id: int, function_id: int, *args: int,
                use_long: bool = False,
                timeout_ms: Optional[int] = None) -> Optional[bytes]:
        self.calls.append((int(feature_id), function_id, tuple(args)))
        val = self._responses.get(self._key(feature_id, function_id, args))
        if val is None:
            val = self._responses.get(
                f"0x{int(feature_id):04x}.{function_id:02x}(*)")
        if val is None:
            return self._missing
        if val.startswith("ERR"):
            return self._raise(val)
        return hexbytes(val)

    @staticmethod
    def _raise(val: str):
        # "ERR 0x02 Invalid argument"
        code = int(val.split()[1], 16)
        raise HIDPPError(code)

    def raw_write_short(self, feature_hi: int, feature_lo: int, *data: int) -> bool:
        self.writes.append((feature_hi, feature_lo, tuple(data)))
        return True
