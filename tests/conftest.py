"""Pytest shared fixtures.

Doesn't require real hardware. Tests that need HID++ responses load
them from ``tests/fixtures/mx4_master4_4.5.0000.json`` (captured from a
live MX Master 4 during v2 development).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make the src/ package importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(scope="session")
def live_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "mx4_master4_4.5.0000.json"
    with path.open() as f:
        return json.load(f)


@pytest.fixture
def feature_cache(live_fixture) -> dict[int, int]:
    return {int(k, 16): v for k, v in live_fixture["device"]["feature_cache"].items()}
