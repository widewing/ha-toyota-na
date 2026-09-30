"""Pure helpers for normalizing Toyota vehicle metadata and state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

_POSITION_STATES = {
    "close": True,
    "closed": True,
    "open": False,
    "opened": False,
}
_LOCK_STATES = {
    "lock": True,
    "locked": True,
    "unlock": False,
    "unlocked": False,
}
_BACKDOOR_TYPES = ("hatch", "trunk", "tailgate")


def endpoint_generation(api_generation: str) -> str:
    """Return the generation name expected by the legacy REST endpoints."""
    if api_generation in ("21MM", "24MM"):
        return "17CYPLUS"
    return api_generation


def has_remote_subscription(vehicle: Mapping[str, Any]) -> bool:
    """Normalize the subscription shapes returned by different API generations."""
    remote_status = vehicle.get("remoteSubscriptionStatus")
    subscription_status = vehicle.get("subscriptionStatus")
    if isinstance(remote_status, str) and remote_status:
        return remote_status.upper() == "ACTIVE"
    if isinstance(subscription_status, str) and subscription_status:
        return subscription_status.upper() in ("ACTIVE", "SUBSCRIBED")
    return vehicle.get("remoteSubscriptionExists") is True


def is_electric_vehicle(vehicle: Mapping[str, Any]) -> bool:
    """Normalize electric-vehicle markers returned by different generations."""
    fuel_type = vehicle.get("fuelType")
    return vehicle.get("evVehicle") is True or (
        isinstance(fuel_type, str) and fuel_type.upper() in ("E", "I")
    )


def first_capability(
    remote: Mapping[str, Any],
    extended: Mapping[str, Any],
    keys: Iterable[str],
) -> bool | None:
    """Return the first explicitly reported capability value."""
    for key in keys:
        if key in remote:
            value = remote[key]
            if isinstance(value, bool):
                return value
        if key in extended:
            value = extended[key]
            if isinstance(value, bool):
                return value
    return None


def normalize_position(value: Any) -> bool | None:
    """Return True for closed, False for open, and None for unknown."""
    if not isinstance(value, str):
        return None
    return _POSITION_STATES.get(value.lower())


def normalize_lock(value: Any) -> bool | None:
    """Return True for locked, False for unlocked, and None for unknown."""
    if not isinstance(value, str):
        return None
    return _LOCK_STATES.get(value.lower())


def normalize_engine_state(value: Any) -> bool | None:
    """Normalize REST and GraphQL engine states, preserving unknown values."""
    normalized = str(value).lower()
    if normalized in ("on", "running", "started", "true", "1"):
        return True
    if normalized in ("off", "stopped", "false", "0"):
        return False
    return None


def normalize_charging_state(value: Any) -> bool | None:
    """Distinguish active charging from waiting, completion, and power supply."""
    normalized = str(value).lower()
    if normalized in ("charging", "40", "56", "active", "in_progress", "in-progress"):
        return True
    if normalized in (
        "12", "36", "45", "60", "unplugged", "charge_now", "resume_charging", "no_controls",
        "unavailable", "external_power_active", "external_power_active_hybrid",
    ):
        return False
    return None


def opening_state_from_values(
    values: Iterable[Mapping[str, Any]],
) -> tuple[bool | None, bool | None]:
    """Extract position and lock state without relying on response order."""
    closed = None
    active_locks = set()
    fallback_locks = set()
    for item in values:
        value = item.get("value")
        if closed is None:
            closed = normalize_position(value)
        locked = normalize_lock(value)
        if locked is not None:
            # A reported locked value can carry status=0.
            if locked or "status" not in item:
                fallback_locks.add(locked)
            if item.get("status") == 1:
                active_locks.add(locked)
    locks = active_locks or fallback_locks
    return closed, next(iter(locks)) if len(locks) == 1 else None


def opening_state_from_graphql(
    opening: Mapping[str, Any],
) -> tuple[bool | None, bool | None]:
    """Extract position and lock state from an AppSync opening object."""
    position = opening.get("position") or {}
    lock = opening.get("lock") or {}
    return normalize_position(position.get("status")), normalize_lock(
        lock.get("status")
    )


def backdoor_candidates(backdoor_type: str | None) -> tuple[str, ...]:
    """Prefer the reported cargo-opening type while retaining compatible fallbacks."""
    if isinstance(backdoor_type, str):
        backdoor_type = backdoor_type.lower()
    if backdoor_type not in _BACKDOOR_TYPES:
        return _BACKDOOR_TYPES
    return (backdoor_type,) + tuple(
        candidate for candidate in _BACKDOOR_TYPES if candidate != backdoor_type
    )


def parse_api_timestamp(value: Any) -> datetime | None:
    """Parse the ISO-8601 timestamp variants returned by Toyota APIs."""
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
        return (
            parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        )
    except ValueError:
        return None
