from ctypes import cast
from datetime import timedelta, datetime
import logging
import asyncio

from toyota_na.auth import ToyotaOneAuth
from toyota_na.client import ToyotaOneClient

# Patch client code
from .patch_client import (
    get_electric_realtime_status,
    get_electric_status,
    api_request,
    _auth_headers,
    get_telemetry,
    get_vehicle_status_17cyplus,
    get_engine_status_17cyplus,
    send_refresh_request_17cyplus,
    remote_request_17cyplus,
    get_vehicle_status_17cy,
    get_engine_status_17cy,
    send_refresh_request_17cy,
    graphql_request,
    graphql_pre_wake,
    graphql_confirm_subscription,
    graphql_refresh_status,
)
ToyotaOneClient.get_electric_realtime_status = get_electric_realtime_status
ToyotaOneClient.get_electric_status = get_electric_status
ToyotaOneClient.api_request = api_request
ToyotaOneClient._auth_headers = _auth_headers
ToyotaOneClient.get_telemetry = get_telemetry
ToyotaOneClient.get_vehicle_status_17cyplus = get_vehicle_status_17cyplus
ToyotaOneClient.get_engine_status_17cyplus = get_engine_status_17cyplus
ToyotaOneClient.send_refresh_request_17cyplus = send_refresh_request_17cyplus
ToyotaOneClient.remote_request_17cyplus = remote_request_17cyplus
ToyotaOneClient.get_vehicle_status_17cy = get_vehicle_status_17cy
ToyotaOneClient.get_engine_status_17cy = get_engine_status_17cy
ToyotaOneClient.send_refresh_request_17cy = send_refresh_request_17cy
ToyotaOneClient.graphql_request = graphql_request
ToyotaOneClient.graphql_pre_wake = graphql_pre_wake
ToyotaOneClient.graphql_confirm_subscription = graphql_confirm_subscription
ToyotaOneClient.graphql_refresh_status = graphql_refresh_status

# Patch base_vehicle
import toyota_na.vehicle.base_vehicle
from .patch_base_vehicle import ApiVehicleGeneration
toyota_na.vehicle.base_vehicle.ApiVehicleGeneration = ApiVehicleGeneration
from .patch_base_vehicle import VehicleFeatures
toyota_na.vehicle.base_vehicle.VehicleFeatures = VehicleFeatures
from .patch_base_vehicle import RemoteRequestCommand
toyota_na.vehicle.base_vehicle.RemoteRequestCommand = RemoteRequestCommand
from .patch_base_vehicle import ToyotaVehicle
toyota_na.vehicle.base_vehicle.ToyotaVehicle = ToyotaVehicle

# Patch seventeen_cy_plus
from toyota_na.vehicle.vehicle_generations.seventeen_cy_plus import SeventeenCYPlusToyotaVehicle
from .patch_seventeen_cy_plus import SeventeenCYPlusToyotaVehicle
toyota_na.vehicle.vehicle_generations.seventeen_cy_plus.SeventeenCYPlusToyotaVehicle = SeventeenCYPlusToyotaVehicle

# Patch seventeen_cy
from toyota_na.vehicle.vehicle_generations.seventeen_cy import SeventeenCYToyotaVehicle
from .patch_seventeen_cy import SeventeenCYToyotaVehicle
toyota_na.vehicle.vehicle_generations.seventeen_cy.SeventeenCYToyotaVehicle = SeventeenCYToyotaVehicle

from toyota_na.exceptions import AuthError, LoginError
from toyota_na.vehicle.base_vehicle import RemoteRequestCommand, ToyotaVehicle

#Patch get_vehicles
from .patch_vehicle import get_vehicles
#from toyota_na.vehicle.vehicle import get_vehicles

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, issue_registry as ir, service
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .websocket_handler import ToyotaWebSocketHandler

from .const import (
    COMMAND_MAP,
    DOMAIN,
    ENGINE_START,
    ENGINE_STOP,
    HAZARDS_ON,
    HAZARDS_OFF,
    DOOR_LOCK,
    DOOR_UNLOCK,
    OPT_EXCLUDED_VINS,
    REFRESH,
    UPDATE_INTERVAL,
    REFRESH_STATUS_INTERVAL,
    VIN_CLAIMS,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["binary_sensor", "button", "device_tracker", "lock", "sensor"]


def _shared_vehicle_issue_id(vin: str, entry_id: str) -> str:
    # Scoped to (vin, entry_id) rather than just vin -- each entry only ever creates/deletes
    # its *own* issue below, never another entry's, which is what keeps this correct with three
    # or more accounts and avoids the winning entry ever deleting a still-valid conflict issue
    # raised by the losing entry (the old vin-only scheme did exactly that).
    return f"shared_vehicle_{vin}_{entry_id}"


def async_claim_vehicles(
    hass: HomeAssistant, entry: ConfigEntry, raw_vehicles: list
) -> list:
    """Filter raw_vehicles down to the ones this entry is allowed to manage.

    A VIN already claimed by a *different* loaded config entry is dropped here rather than
    proceeding to entity creation. This is what keeps a vehicle visible to two Toyota accounts
    (Toyota "family sharing") from ever colliding: only one entry's platforms ever see it, so
    unique_id/device identifiers never need to differ by account, and no entity ends up silently
    bound to the wrong account's session.

    Called on every refresh for every entry (there's deliberately no pre-filter skipping
    already-claimed VINs before this): that's what lets a losing entry keep re-asserting its own
    Repair issue every cycle, and correctly clear it once the conflict resolves, instead of going
    silent after its first loss. The cost is a losing entry keeps polling (then discarding) a
    vehicle it doesn't own until the user excludes it via the Configure option -- accepted, since
    that's exactly the window this feature exists to shorten.
    """
    vin_claims: dict[str, str] = hass.data[DOMAIN].setdefault(VIN_CLAIMS, {})
    claimed = []
    for vehicle in raw_vehicles:
        owner = vin_claims.get(vehicle.vin)
        if owner is not None and owner != entry.entry_id:
            other_entry = hass.config_entries.async_get_entry(owner)
            other_title = other_entry.title if other_entry else "another account"
            _LOGGER.warning(
                "VIN ...%s (%s %s) is already managed by another Toyota (North America) "
                "account (%s) in this Home Assistant instance; skipping it here. If this is a "
                "family-shared vehicle, use this integration's Configure option to choose which "
                "account should manage it.",
                vehicle.vin[-4:],
                vehicle.model_year,
                vehicle.model_name,
                other_title,
            )
            ir.async_create_issue(
                hass,
                DOMAIN,
                _shared_vehicle_issue_id(vehicle.vin, entry.entry_id),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="shared_vehicle",
                translation_placeholders={
                    "vehicle": f"{vehicle.model_year} {vehicle.model_name}",
                    "this_account": entry.title,
                    "managing_account": other_title,
                },
            )
            continue
        vin_claims[vehicle.vin] = entry.entry_id
        # Only ever clear an issue *this* entry raised about not owning the vehicle -- never
        # another entry's, since we have no way to know whether the conflict still exists from
        # their perspective.
        ir.async_delete_issue(hass, DOMAIN, _shared_vehicle_issue_id(vehicle.vin, entry.entry_id))
        claimed.append(vehicle)
    return claimed


def async_release_vehicle_claims(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Release any VINs this entry claimed (so another entry can adopt them), and clean up any
    Repair issues this entry raised about vehicles it *doesn't* own.

    The second half matters on its own: if this entry never claimed anything (it was always the
    losing side of a conflict) but gets removed or disabled, nothing else would ever clean up the
    issue it raised -- it would otherwise linger in the registry forever, since only this entry's
    own next refresh could have cleared it, and that will never happen again.
    """
    vin_claims: dict[str, str] = hass.data.get(DOMAIN, {}).get(VIN_CLAIMS, {})
    for vin in [v for v, owner in vin_claims.items() if owner == entry.entry_id]:
        del vin_claims[vin]

    issue_registry = ir.async_get(hass)
    suffix = f"_{entry.entry_id}"
    for (issue_domain, issue_id) in list(issue_registry.issues.keys()):
        if issue_domain == DOMAIN and issue_id.endswith(suffix):
            ir.async_delete_issue(hass, DOMAIN, issue_id)


def async_prune_unclaimed_devices(
    hass: HomeAssistant, entry: ConfigEntry, vins_to_prune: set
) -> None:
    """Remove this entry's device for each VIN in vins_to_prune -- vehicles the user just
    excluded via the Configure option, or vehicles just lost to another entry in a claim
    conflict this refresh. Removing the device also removes its entities (Home Assistant's
    entity registry listens for device removal and drops any entity whose config entry matches).

    Deliberately NOT "every device whose VIN isn't in this refresh's vehicle list" -- a config
    entry's devices persist across refreshes, but the vehicle list itself can legitimately come
    back short (or empty) on a single poll without raising (a Toyota API hiccup, a transient
    partial response). Since no platform here re-creates an entity once its device is removed
    (entities are only ever created in each platform's async_setup_entry), pruning on mere
    absence would delete real, working entities over a one-poll blip, with nothing bringing them
    back short of a full entry reload. Pruning only for reasons we can positively confirm --  an
    explicit exclusion, or a claim genuinely lost this cycle -- avoids that risk entirely. A
    vehicle that's actually gone from the account (e.g. sold) isn't covered by this at all; the
    user removes that one manually from its device page instead, which
    async_remove_config_entry_device() below allows.
    """
    if not vins_to_prune:
        return
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        vin = next((ident[1] for ident in device.identifiers if ident[0] == DOMAIN), None)
        if vin is not None and vin in vins_to_prune:
            device_registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Let a user manually delete a device from its device page -- the escape hatch for a
    vehicle async_prune_unclaimed_devices() deliberately won't touch on its own: one that's
    disappeared from the Toyota account entirely (e.g. sold), rather than being excluded or lost
    to a claim conflict. Unconditionally allowed: if the vehicle is actually still in this
    entry's managed set, get_vehicles()/async_claim_vehicles() will just recreate the device on
    the entry's next refresh, the same as manually deleting any other still-present device would.
    """
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry, but only if the vehicle-exclusion option actually changed.

    Home Assistant fires config-entry update listeners on *any* change to the entry -- data,
    options, or title -- not just options (see ConfigEntries.async_update_entry's docstring).
    This integration writes entry.data routinely at runtime (refreshed auth tokens roughly every
    5-10 minutes, a last_refreshed_at timestamp every couple hours), and a naive listener would
    force a full reload -- tearing down the coordinator, WebSocket connection, and every entity --
    on that cadence, for every user, not just ones using the vehicle-exclusion feature. Comparing
    against the exclusion-list snapshot taken at setup keeps this a no-op for everyone except an
    actual options-flow submission.
    """
    entry_runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry_runtime is None:
        return
    new_excluded = set(entry.options.get(OPT_EXCLUDED_VINS, []))
    if entry_runtime.get("excluded_vins_snapshot") == new_excluded:
        return
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup(hass: HomeAssistant, _processed_config) -> bool:
    @service.verify_domain_control(DOMAIN)
    async def async_service_handle(service_call: ServiceCall) -> None:
        """Handle dispatched services."""

        device_registry = dr.async_get(hass)
        device = device_registry.async_get(service_call.data["vehicle"])
        remote_action = service_call.service

        if device is None:
            _LOGGER.warning("Device does not exist")
            return

        if len(device.config_entries) == 0:
            _LOGGER.warning("Device missing config entry")
            return

        vin = next((ident[1] for ident in device.identifiers if ident[0] == DOMAIN), None)
        if vin is None:
            _LOGGER.warning("Device has no %s identifier", DOMAIN)
            return

        # A device can still list a config entry that's been unloaded but not removed (HA only
        # drops an entry from a shared device's config_entries on full removal, not on unload),
        # and with two Toyota accounts sharing a vehicle, a device can legitimately list an entry
        # that has never had -- and will never have -- this VIN in its coordinator data (the
        # losing side of a family-sharing claim). Resolve by finding whichever entry's
        # coordinator actually has this VIN, instead of trusting the last-iterated entry_id.
        coordinator = None
        for entry_id in device.config_entries:
            entry_runtime = hass.data.get(DOMAIN, {}).get(entry_id)
            if not entry_runtime or "coordinator" not in entry_runtime:
                continue
            candidate = entry_runtime["coordinator"]
            if candidate.data and any(v.vin == vin for v in candidate.data):
                coordinator = candidate
                break

        if coordinator is None:
            _LOGGER.warning("No loaded config entry currently manages VIN ...%s", vin[-4:])
            return

        # REFRESH and every other command (lock, hazards, engine start/stop) are handled in one
        # loop/if-elif rather than as separate functions because they share the vin-matching
        # loop and the trailing log line -- REFRESH's branch is a different call path
        # (poll_vehicle_refresh() + a manual coordinator nudge, see the TODO below) than the
        # generic send_command() path every other service uses.
        for vehicle in coordinator.data:
            if vehicle.vin == vin and remote_action.upper() == "REFRESH" and vehicle.subscribed:
                await vehicle.poll_vehicle_refresh()
                # TODO: This works great and prevents us from unnecessarily hitting Toyota. But we can and should
                # probably do stuff like this in the library where we can better control which APIs we hit to refresh our in-memory data.
                # Same delayed-refresh pattern as button.py's ToyotaCommandButton/ToyotaRefreshButton --
                # see the comments there for why the sleep and the extra async_set_updated_data exist.
                coordinator.async_set_updated_data(coordinator.data)
                await asyncio.sleep(10)
                await coordinator.async_request_refresh()
            elif vehicle.vin == vin and vehicle.subscribed:
                command = COMMAND_MAP[remote_action]
                if not vehicle.supports_command(command):
                    _LOGGER.warning(
                        "Skipping %s for %s: Toyota reports this vehicle does not support this command",
                        remote_action,
                        vin,
                    )
                    break
                await vehicle.send_command(command)
                break

        _LOGGER.info("Handling service call %s for %s ", remote_action, vin)
        return

    hass.services.async_register(DOMAIN, ENGINE_START, async_service_handle)
    hass.services.async_register(DOMAIN, ENGINE_STOP, async_service_handle)
    hass.services.async_register(DOMAIN, HAZARDS_ON, async_service_handle)
    hass.services.async_register(DOMAIN, HAZARDS_OFF, async_service_handle)
    hass.services.async_register(DOMAIN, DOOR_LOCK, async_service_handle)
    hass.services.async_register(DOMAIN, DOOR_UNLOCK, async_service_handle)
    hass.services.async_register(DOMAIN, REFRESH, async_service_handle)

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})

    client = ToyotaOneClient(
        ToyotaOneAuth(
            initial_tokens=entry.data["tokens"],
            callback=lambda tokens: update_tokens(tokens, hass, entry),
        )
    )
    try:
        client.auth.set_tokens(entry.data["tokens"])
        await client.auth.check_tokens()
    except AuthError as e:
        _LOGGER.exception(e)
        raise ConfigEntryAuthFailed(e) from e

    # Reuse a stable device ID across restarts instead of letting a fresh one get generated
    # every time. Without this, every HA restart (and every standalone script run during
    # development) looks to Toyota like a brand new, never-before-seen device -- and Toyota's
    # backend appears to cap how many concurrent devices can hold an active subscription per
    # vehicle (see the "device limit exceeded?" handling in websocket_handler.py), so repeated
    # restarts during development can plausibly exhaust that cap on their own.
    if "device_id" in entry.data:
        client.auth.set_device_id(entry.data["device_id"])
    else:
        entry_data = dict(entry.data)
        entry_data["device_id"] = client.auth.get_device_id()
        hass.config_entries.async_update_entry(entry, data=entry_data)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=lambda: update_vehicles_status(hass, client, entry),
        update_interval=timedelta(seconds=UPDATE_INTERVAL),
    )

    # From here on, this entry may end up holding VIN claims -- async_config_entry_first_refresh()
    # below calls update_vehicles_status(), which claims vehicles as a side effect before it can
    # fail on something unrelated later in the same call (e.g. writing the refreshed entry data).
    # Anything that can still fail through the end of setup must release those claims on the way
    # out -- otherwise a claim can outlive the entry that holds it, permanently blocking the
    # vehicle from ever being claimed by another entry.
    try:
        await coordinator.async_config_entry_first_refresh()

        # Start WebSocket handler for vehicle status push notifications. Only for 21MM/24MM --
        # 17CYPLUS is confirmed to work fully via REST alone (verified via live testing), so
        # there's no reason to open a WebSocket connection for it. 21MM/24MM keep it as a
        # fallback: this integration is used by vehicles we haven't personally tested, and REST
        # working for our own 21MM vehicle (once account permissions and the value-shape parsing
        # were fixed) isn't proof it's sufficient for every account/vehicle combination on this
        # generation.
        ws_handler = ToyotaWebSocketHandler(client)
        vins = (
            [
                v.vin
                for v in coordinator.data
                if v.subscribed and v.api_generation != ApiVehicleGeneration.CY17PLUS.value
            ]
            if coordinator.data
            else []
        )
        if vins:
            await ws_handler.start(vins)
        client._ws_handler = ws_handler

        hass.data[DOMAIN][entry.entry_id] = {
            "toyota_na_client": client,
            "coordinator": coordinator,
            "ws_handler": ws_handler,
            # Snapshot of the exclusion option as of this setup, so async_update_options() can
            # tell an actual options-flow change apart from the routine entry.data writes
            # (token refresh, last_refreshed_at) that also fire the update listener.
            "excluded_vins_snapshot": set(entry.options.get(OPT_EXCLUDED_VINS, [])),
        }

        entry.async_on_unload(entry.add_update_listener(async_update_options))

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        async_release_vehicle_claims(hass, entry)
        raise

    return True


def update_tokens(tokens: dict[str, str], hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.info("Tokens refreshed, updating ConfigEntry")
    data = dict(entry.data)
    data["tokens"] = tokens
    hass.config_entries.async_update_entry(entry, data=data)


async def update_vehicles_status(hass: HomeAssistant, client: ToyotaOneClient, entry: ConfigEntry):
    need_refresh = False
    need_refresh_before = datetime.utcnow().timestamp() - REFRESH_STATUS_INTERVAL
    if "last_refreshed_at" not in entry.data or entry.data["last_refreshed_at"] < need_refresh_before:
        need_refresh = True
    try:
        _LOGGER.debug("Updating vehicle status")

        # Only the user's explicit exclusions pre-filter get_vehicles() -- vehicles claimed by
        # another entry are deliberately NOT pre-filtered here. async_claim_vehicles() below is
        # the sole, unconditional authority on every refresh; letting it re-examine every VIN
        # every cycle (rather than skipping ones lost last time) is what lets a losing entry
        # keep re-asserting or clearing its own Repair issue as the conflict evolves.
        user_excluded_vins = set(entry.options.get(OPT_EXCLUDED_VINS, []))
        for vin in user_excluded_vins:
            # An explicit exclusion resolves any prior conflict from this entry's side.
            ir.async_delete_issue(hass, DOMAIN, _shared_vehicle_issue_id(vin, entry.entry_id))

        fetched_vehicles = await get_vehicles(client, exclude_vins=user_excluded_vins)
        raw_vehicles = async_claim_vehicles(hass, entry, fetched_vehicles)
        # Vehicles this entry actually fetched (so we know they still exist on the account) but
        # didn't win the claim for this cycle -- distinct from a vehicle simply missing from a
        # possibly-incomplete fetch. See async_prune_unclaimed_devices() for why this distinction
        # matters.
        lost_to_conflict = {v.vin for v in fetched_vehicles} - {v.vin for v in raw_vehicles}

        vehicles: list[ToyotaVehicle] = []
        for vehicle in raw_vehicles:
            if vehicle.subscribed is not True:
                _LOGGER.warning(
                    f"Your {vehicle.model_year} {vehicle.model_name} needs a remote services subscription to fully work with Home Assistant."
                )
            if need_refresh and vehicle.subscribed:
                try:
                    _LOGGER.info(
                        "Requesting vehicle refresh for %s %s",
                        vehicle.model_year,
                        vehicle.model_name,
                    )
                    await vehicle.poll_vehicle_refresh()
                except Exception as e:
                    _LOGGER.warning("Vehicle refresh failed (%s), continuing without refresh", e)
            vehicles.append(vehicle)
        async_prune_unclaimed_devices(hass, entry, user_excluded_vins | lost_to_conflict)
        entry_data = dict(entry.data)
        if need_refresh:
            entry_data["last_refreshed_at"] = datetime.utcnow().timestamp()
        hass.config_entries.async_update_entry(entry, data=entry_data)
        return vehicles
    except AuthError as e:
        try:
            client.auth.login(entry.data["username"], entry.data["password"])
        except LoginError:
            _LOGGER.exception("Error logging in")
            raise ConfigEntryAuthFailed(e) from e
    except Exception as e:
        _LOGGER.exception("Error fetching data")
        raise UpdateFailed(e) from e


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    # Stop WebSocket handler
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    ws_handler = entry_data.get("ws_handler")
    if ws_handler:
        await ws_handler.stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        async_release_vehicle_claims(hass, entry)

    return unload_ok
