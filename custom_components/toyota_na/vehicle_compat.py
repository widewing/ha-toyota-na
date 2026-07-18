"""Compatibility helpers for Toyota vehicle discovery and live status values."""

from typing import Optional


_ACTIVE_SUBSCRIPTION_STATES = {"active", "subscribed"}
_REMOTE_CAPABILITIES = {
    "doorLockUnlockCapable",
    "remoteEngineStartStop",
}
_ELECTRIFIED_FUEL_TYPES = {"E", "I"}
_CLOSED_STATES = {"close", "closed"}
_OPEN_STATES = {"open", "opened"}
_LOCKED_STATES = {"lock", "locked"}
_UNLOCKED_STATES = {"unlock", "unlocked"}


def has_remote_subscription(vehicle: dict) -> bool:
    """Return whether Toyota reports Remote Connect for a vehicle.

    Newer vehicle-list responses do not always set
    ``remoteSubscriptionStatus``. The current app also accepts the general
    subscription state, the explicit existence flag, or a remote capability.
    """
    states = (
        vehicle.get("remoteSubscriptionStatus"),
        vehicle.get("subscriptionStatus"),
    )
    if any(
        isinstance(state, str) and state.strip().lower() in _ACTIVE_SUBSCRIPTION_STATES
        for state in states
    ):
        return True

    if vehicle.get("remoteSubscriptionExists") is True:
        return True

    capabilities = vehicle.get("extendedCapabilities")
    if not isinstance(capabilities, dict):
        return False
    return any(capabilities.get(name) is True for name in _REMOTE_CAPABILITIES)


def is_electric_vehicle(vehicle: dict) -> bool:
    """Return whether the vehicle exposes EV/PHEV charging information."""
    if vehicle.get("evVehicle") is True:
        return True
    fuel_type = vehicle.get("fuelType")
    return (
        isinstance(fuel_type, str)
        and fuel_type.strip().upper() in _ELECTRIFIED_FUEL_TYPES
    )


def infer_backdoor_type(vehicle: dict) -> str:
    """Return the AppSync backdoor capability value for subscription setup."""
    backdoor_type = vehicle.get("backdoorType")
    if isinstance(backdoor_type, str) and backdoor_type.strip():
        return backdoor_type.strip()

    model_name = str(vehicle.get("modelName", "")).lower()
    hatch_models = (
        "rav4",
        "corolla cross",
        "highlander",
        "grand highlander",
        "venza",
        "bz4x",
        "4runner",
        "sequoia",
        "sienna",
    )
    return "hatch" if any(name in model_name for name in hatch_models) else "trunk"


def closed_from_status(value: object) -> Optional[bool]:
    """Normalize classic and 24MM opening states to a closed boolean."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in _CLOSED_STATES:
        return True
    if normalized in _OPEN_STATES:
        return False
    return None


def locked_from_status(value: object) -> Optional[bool]:
    """Normalize classic and 24MM lock states to a locked boolean."""
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in _LOCKED_STATES:
        return True
    if normalized in _UNLOCKED_STATES:
        return False
    return None
