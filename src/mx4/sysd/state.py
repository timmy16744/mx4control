"""Aggregate device state and mirror it to /run for clients."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from ..config.paths import runtime_state_path
from ..hidpp.device import MXMaster4

logger = logging.getLogger(__name__)


def build_state(device: Optional[MXMaster4], info: Optional[dict]) -> dict[str, Any]:
    """Snapshot every live hardware property for D-Bus clients & UI."""
    if device is None:
        return {"connected": False}
    state: dict[str, Any] = {"connected": True}
    try:
        di = device.get_device_info()
        if di:
            state.update(
                name=di.name,
                friendly_name=di.friendly_name or di.name,
                firmware=di.firmware_version,
                battery=di.battery_level,
                battery_bucket=di.battery_bucket,
                battery_level_name=di.battery_level_name,
                charging=di.battery_charging,
                battery_status=di.battery_status,
                connection=di.connection_type,
            )

        # SmartShift + MagSpeed wheel mode + ratchet torque
        ss = device.get_smartshift_state()
        state.update(
            smartshift=ss.smartshift_enabled,
            smartshift_threshold=ss.threshold,
            wheel_mode=ss.mode_name,
            ratchet_torque=ss.tuned_torque,
            tunable_torque=ss.tunable_torque,
            default_torque=ss.default_torque,
        )

        # Hi-res vertical scroll + HD smooth scroll tuning
        hires_en, hires_inv, hires_div = device.get_hires_scroll()
        state["hires_enabled"] = hires_en
        state["hires_invert"] = hires_inv
        state["hires_diverted"] = hires_div

        # Thumb wheel (0x2150) — status + hardware native vs diverted resolution
        tw_div, tw_inv = device.get_thumbwheel_status()
        state["thumbwheel_diverted"] = tw_div
        state["thumbwheel_invert"] = tw_inv
        tw_info = device.get_thumbwheel_info()
        if tw_info:
            state["thumbwheel_native_res"] = int(tw_info.get("native_res", 20))
            state["thumbwheel_diverted_res"] = int(tw_info.get("diverted_res", 120))
            state["thumbwheel_res_ratio"] = float(tw_info.get("resolution_ratio", 6.0))
            state["thumbwheel_has_touch"] = bool(tw_info.get("has_touch", False))
            state["thumbwheel_has_timestamp"] = bool(tw_info.get("has_timestamp", False))

        # DPI + range
        state["dpi"] = device.get_dpi()
        dpi_min, dpi_max, dpi_step = device.get_dpi_range()
        state["dpi_min"] = dpi_min
        state["dpi_max"] = dpi_max
        state["dpi_step"] = dpi_step

        # Haptics (0x19B0)
        hap_en, hap_lvl = device.get_haptic()
        hap_caps = device.get_haptic_capabilities()
        state["haptic_enabled"] = hap_en
        state["haptic_level"] = hap_lvl
        state["haptic_discrete"] = hap_caps.discrete_levels
        state["haptic_waveforms"] = list(hap_caps.waveforms)

        # Force-sensing thumb pad (0x19C0)
        fb = device.get_force_button(0)
        if fb is not None:
            state.update(
                force_supported=True,
                force_changeable=fb.changeable,
                force_value=fb.current_force,
                force_min=fb.min_force,
                force_max=fb.max_force,
                force_default=fb.default_force,
            )
        else:
            state["force_supported"] = False

        # Easy-Switch hosts
        hosts = device.get_hosts()
        if hosts:
            state["current_host"] = hosts.current_host
            state["num_hosts"] = hosts.num_hosts
            state["can_rename_hosts"] = hosts.can_set_name
    except Exception as e:
        logger.warning("build_state partial (%s)", e)
    if info:
        state.setdefault("connection", info.get("connection_type", "bolt"))
    return state


def write_state_file(state: dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or runtime_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, path)
    except Exception as e:
        logger.debug("could not write state file %s: %s", path, e)
