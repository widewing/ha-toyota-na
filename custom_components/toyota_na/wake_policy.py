"""Vehicle wake policy helpers."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

CONF_WAKE_INTERVAL = "automatic_wake_interval"
LAST_WAKE_AT = "last_refreshed_at"
LAST_VEHICLE_WAKES = "last_vehicle_wakes"
VEHICLE_WAKE_TIMESTAMP = "timestamp"

WAKE_INTERVAL_OPTIONS = {
    0: "Cloud updates only",
    2 * 3600: "Every 2 hours",
    6 * 3600: "Every 6 hours",
    12 * 3600: "Every 12 hours",
    24 * 3600: "Every 24 hours",
}


def automatic_wake_interval(
    options: Mapping[str, Any], default_interval: int
) -> int:
    """Return a valid configured wake interval in seconds."""
    interval = options.get(CONF_WAKE_INTERVAL, default_interval)
    if type(interval) is not int or interval < 0:
        return default_interval
    return interval


def automatic_wake_due(
    entry_data: Mapping[str, Any],
    options: Mapping[str, Any],
    default_interval: int,
    *,
    vin: str | None = None,
    now: float | None = None,
) -> bool:
    """Return whether Home Assistant should request a vehicle wake."""
    interval = automatic_wake_interval(options, default_interval)
    if interval == 0:
        return False

    last_wake_at = None
    vehicle_wakes = entry_data.get(LAST_VEHICLE_WAKES)
    if vin is not None and isinstance(vehicle_wakes, list):
        for record in vehicle_wakes:
            if isinstance(record, Mapping) and record.get("vin") == vin:
                last_wake_at = record.get(VEHICLE_WAKE_TIMESTAMP)
                break
    else:
        # Entries created before per-vehicle tracking retain their previous
        # schedule until the first vehicle-specific wake is recorded.
        last_wake_at = entry_data.get(LAST_WAKE_AT)

    if not isinstance(last_wake_at, (int, float)) or isinstance(last_wake_at, bool):
        return True

    current_time = time.time() if now is None else now
    return last_wake_at <= current_time - interval


def record_vehicle_wake(
    hass: Any,
    entry: Any,
    vin: str | None = None,
    *,
    now: float | None = None,
) -> None:
    """Persist when a vehicle wake was last requested."""
    timestamp = time.time() if now is None else now
    entry_data = dict(entry.data)
    entry_data[LAST_WAKE_AT] = timestamp

    if vin is not None:
        vehicle_wakes = []
        stored_wakes = entry_data.get(LAST_VEHICLE_WAKES)
        for record in stored_wakes if isinstance(stored_wakes, list) else ():
            if (
                isinstance(record, Mapping)
                and isinstance(record.get("vin"), str)
                and record.get("vin") != vin
            ):
                vehicle_wakes.append(dict(record))
        vehicle_wakes.append(
            {"vin": vin, VEHICLE_WAKE_TIMESTAMP: timestamp}
        )
        entry_data[LAST_VEHICLE_WAKES] = vehicle_wakes

    hass.config_entries.async_update_entry(entry, data=entry_data)
