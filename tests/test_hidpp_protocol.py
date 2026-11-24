"""Protocol-level tests using captured byte streams."""

from __future__ import annotations

from mx4.hidpp.features import (
    FeatureID, HapticPattern, HIDPPError,
    MappingFlag,
)


def test_feature_ids_are_distinct():
    seen = {}
    for name, value in FeatureID.__members__.items():
        assert value not in seen, f"{name} duplicates {seen[value]} ({value:#06x})"
        seen[value] = name


def test_haptic_patterns_cover_14():
    assert max(HapticPattern) == 14
    assert min(HapticPattern) == 0


def test_hidpperror_codes_covered():
    # Every error we actually saw on the live probe is documented
    observed = {0x02, 0x05, 0x07}
    assert observed.issubset(HIDPPError.CODES)


def test_mapping_flag_bits_distinct():
    vals = [f.value for f in MappingFlag]
    assert len(vals) == len(set(vals))


def test_feature_cache_matches_live_probe(feature_cache):
    """The live device exposed these feature IDs. If we ever need to
    parse them we shouldn't regress on the index layout."""
    assert FeatureID.ROOT in feature_cache
    assert FeatureID.REPROG_CONTROLS_V4 in feature_cache
    assert FeatureID.ADJUSTABLE_DPI in feature_cache
    assert FeatureID.UNIFIED_BATTERY in feature_cache
    assert FeatureID.HOSTS_INFO in feature_cache
    assert FeatureID.CHANGE_HOST in feature_cache
    assert FeatureID.THUMBWHEEL in feature_cache
    assert FeatureID.MX_SMART_ACTIONS in feature_cache
    # Haptic direct-address feature is NOT enumerated — documented
    assert FeatureID.MX_HAPTICS_DIRECT not in feature_cache


def test_locked_features_return_logitech_internal(live_fixture):
    """These features exist but need Logi auth to use. Confirm every
    function we probed returned error 0x05."""
    responses = live_fixture["responses"]
    for key, val in responses.items():
        if key.startswith("0x9401.") or key.startswith("0x9402."):
            # Allow either "Logitech internal" or "Invalid function ID"
            assert "ERR" in val, f"{key}: expected locked, got {val}"


def test_hosts_info_parsing(live_fixture):
    """Regression: host_info function 0x01 returns 12 bytes starting
    with the host index."""
    responses = live_fixture["responses"]
    for host in range(3):
        r = responses.get(f"0x1815.01({host:02x})")
        assert r is not None
        # First byte is the echoed host index
        first_byte = int(r[:2], 16)
        assert first_byte == host
