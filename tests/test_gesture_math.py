"""Gesture geometry regression tests."""

from __future__ import annotations

import pytest

from mx4.daemon.gesture import _segment_for, SEGMENT_COUNT


@pytest.mark.parametrize("dx,dy,expected", [
    (0, 0, None),
    (5, 5, None),          # inside cancel radius
    (0, -200, 0),          # straight up
    (200, -200, 1),        # top-right
    (200, 0, 2),           # right
    (200, 200, 3),         # bottom-right
    (0, 200, 4),           # down
    (-200, 200, 5),        # bottom-left
    (-200, 0, 6),          # left
    (-200, -200, 7),       # top-left
])
def test_segment_mapping(dx, dy, expected):
    assert _segment_for(dx, dy) == expected


def test_cancel_zone_radius():
    # Just inside the cancel radius → None
    assert _segment_for(30, 0) is None
    # Just outside → segment 2 (right)
    assert _segment_for(60, 0) == 2


def test_all_eight_segments_reachable():
    seen = set()
    for angle_deg in range(0, 360, 5):
        import math
        r = 200
        a = math.radians(angle_deg - 90)  # 0deg = up
        dx, dy = int(r * math.cos(a)), int(r * math.sin(a))
        s = _segment_for(dx, dy)
        if s is not None:
            seen.add(s)
    assert seen == set(range(SEGMENT_COUNT))
