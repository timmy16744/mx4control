"""Apply persistent device settings on connect.

Called by the supervisor every time the mouse attaches (or reconnects via
0x1D4B WIRELESS_DEVICE_STATUS) — so DPI, scroll mode, SmartShift threshold,
MagSpeed ratchet torque, hi-res scrolling, thumb-wheel diversion/invert,
haptic power/level, thumb-pad force threshold, and persistent button remaps
are re-asserted at boot, after suspend, and after Easy-Switch host changes.
"""

from __future__ import annotations

import logging

from ..config.schema import DeviceConfig
from ..hidpp.device import MXMaster4
from ..hidpp.features import WheelMode

logger = logging.getLogger(__name__)


def apply_persistent_settings(
    device: MXMaster4,
    cfg: DeviceConfig,
    *,
    divert_wheel: bool = False,
    divert_thumbwheel_hd: bool = False,
) -> dict[str, bool]:
    """Push every device-scope setting to the mouse. Returns per-area ok flags."""
    results: dict[str, bool] = {}

    results["dpi"] = device.set_dpi(cfg.dpi)

    # Determine scroll mode: wheel_mode takes precedence when free, otherwise
    # honour smartshift_enabled so legacy configs and tests stay consistent.
    mode = (cfg.wheel_mode or ("smart" if cfg.smartshift_enabled else "ratchet")).lower()
    if mode == "free":
        results["smartshift"] = device.set_scroll_mode(
            "free", cfg.smartshift_threshold, torque=cfg.ratchet_torque,
        )
    elif cfg.smartshift_enabled or mode == "smart":
        results["smartshift"] = device.set_smartshift(
            True, cfg.smartshift_threshold,
            wheel_mode=WheelMode.RATCHET,
            torque=cfg.ratchet_torque,
        )
    else:
        # SmartShift OFF + ratchet mode (stops the clutch buzz)
        results["smartshift"] = device.set_smartshift(
            False, cfg.smartshift_threshold,
            wheel_mode=WheelMode.RATCHET,
            torque=cfg.ratchet_torque,
        )

    # When diverted to SmoothScrollEngine, keep hardware invert=False so software
    # handles inversion once (preventing double-inversion!).
    hw_invert = False if divert_wheel else cfg.hires_invert
    results["hires"] = device.set_hires_scroll(
        cfg.hires_enabled or divert_wheel, hw_invert, diverted=divert_wheel,
    )
    # Thumb wheel (0x2150):
    # - hd_scroll: divert hardware with invert=False (HorizontalScrollEngine handles invert once)
    # - actions:   divert hardware with cfg.thumbwheel_invert for mx4-agent ThumbWheelHandler
    # - native:    firmware passthrough with cfg.thumbwheel_invert
    tw_mode = (cfg.thumbwheel_mode or ("actions" if cfg.thumbwheel_diverted else "native")).lower()
    if divert_thumbwheel_hd and tw_mode == "hd_scroll":
        tw_div, tw_hw_invert = True, False
    elif tw_mode == "actions" or (tw_mode == "native" and cfg.thumbwheel_diverted):
        tw_div, tw_hw_invert = True, cfg.thumbwheel_invert
    else:
        tw_div, tw_hw_invert = False, cfg.thumbwheel_invert
    results["thumbwheel"] = device.set_thumbwheel_diverted(tw_div, tw_hw_invert)
    results["haptic"] = device.set_haptic(cfg.haptic_enabled, cfg.haptic_level)

    if cfg.force_threshold > 0:
        results["force"] = device.set_force_button(cfg.force_threshold)

    for b in cfg.buttons:
        if b.mode == "remap" and b.target:
            results[f"button_{b.cid:#06x}"] = device.remap_button(b.cid, b.target)
        elif b.mode == "disabled":
            results[f"button_{b.cid:#06x}"] = device.divert_button(b.cid, True)

    if cfg.restore_host:
        results["host"] = device.switch_host(cfg.preferred_host)

    ok = sum(1 for v in results.values() if v)
    logger.info(
        "applied device settings: %d/%d ok (mode=%s smartshift=%s dpi=%d haptic=%s/%d%%)",
        ok, len(results), mode, cfg.smartshift_enabled, cfg.dpi,
        cfg.haptic_enabled, cfg.haptic_level,
    )
    return results
