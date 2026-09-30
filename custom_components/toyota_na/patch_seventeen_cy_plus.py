import logging
from typing import Optional

from toyota_na.client import ToyotaOneClient
from toyota_na.vehicle.base_vehicle import (
    ApiVehicleGeneration,
    RemoteRequestCommand,
    ToyotaVehicle,
    VehicleFeatures,
)
from toyota_na.vehicle.entity_types.ToyotaLocation import ToyotaLocation
from toyota_na.vehicle.entity_types.ToyotaLockableOpening import ToyotaLockableOpening
from toyota_na.vehicle.entity_types.ToyotaNumeric import ToyotaNumeric
from toyota_na.vehicle.entity_types.ToyotaOpening import ToyotaOpening
from toyota_na.vehicle.entity_types.ToyotaRemoteStart import ToyotaRemoteStart

from .vehicle_helpers import (
    backdoor_candidates,
    normalize_charging_state,
    normalize_engine_state,
    opening_state_from_graphql,
    opening_state_from_values,
    parse_api_timestamp,
)

_LOGGER = logging.getLogger(__name__)


class SeventeenCYPlusToyotaVehicle(ToyotaVehicle):

    _has_remote_subscription = False
    _has_electric = False
    _command_map = {
        RemoteRequestCommand.DoorLock: "door-lock",
        RemoteRequestCommand.DoorUnlock: "door-unlock",
        RemoteRequestCommand.EngineStart: "engine-start",
        RemoteRequestCommand.EngineStop: "engine-stop",
        RemoteRequestCommand.HazardsOn: "hazard-on",
        RemoteRequestCommand.HazardsOff: "hazard-off",
        RemoteRequestCommand.VehicleFinder: "find-vehicle",
        RemoteRequestCommand.Refresh: "refresh",
    }

    #  We'll parse these keys out in the parser by mapping the category and section types to a string literal
    _vehicle_status_category_map = {
        "Driver Side Door": VehicleFeatures.FrontDriverDoor,
        "Driver Side Window": VehicleFeatures.FrontDriverWindow,
        "Passenger Side Door": VehicleFeatures.FrontPassengerDoor,
        "Passenger Side Window": VehicleFeatures.FrontPassengerWindow,
        "Driver Side Rear Door": VehicleFeatures.RearDriverDoor,
        "Driver Side Rear Window": VehicleFeatures.RearDriverWindow,
        "Passenger Side Rear Door": VehicleFeatures.RearPassengerDoor,
        "Passenger Side Rear Window": VehicleFeatures.RearPassengerWindow,
        "Other Hatch": VehicleFeatures.Trunk,
        "Other Trunk": VehicleFeatures.Trunk,
        "Other Moonroof": VehicleFeatures.Moonroof,
        "Other Hood": VehicleFeatures.Hood,
    }

    _vehicle_telemetry_map = {
        "distanceToEmpty": VehicleFeatures.DistanceToEmpty,
        "flTirePressure": VehicleFeatures.FrontDriverTire,
        "frTirePressure": VehicleFeatures.FrontPassengerTire,
        "rlTirePressure": VehicleFeatures.RearDriverTire,
        "rrTirePressure": VehicleFeatures.RearPassengerTire,
        "fuelLevel": VehicleFeatures.FuelLevel,
        "odometer": VehicleFeatures.Odometer,
        "spareTirePressure": VehicleFeatures.SpareTirePressure,
        "tripA": VehicleFeatures.TripDetailsA,
        "tripB": VehicleFeatures.TripDetailsB,
        "nextService": VehicleFeatures.NextService,
        "speed": VehicleFeatures.Speed,

        "driverWindow": VehicleFeatures.FrontDriverWindow,
        "passengerWindow": VehicleFeatures.FrontPassengerWindow,
        "rlWindow": VehicleFeatures.RearDriverWindow,
        "rrWindow": VehicleFeatures.RearPassengerWindow,
        "sunRoof": VehicleFeatures.Moonroof,
    }

    def __init__(
        self,
        client: ToyotaOneClient,
        has_remote_subscription: bool,
        has_electric: bool,
        model_name: str,
        model_year: str,
        vin: str,
        region: str,
        generation: ApiVehicleGeneration = ApiVehicleGeneration.CY17PLUS,
        brand: str = "T",
        backdoor_type: Optional[str] = None,
        remote_capabilities: Optional[dict] = None,
        extended_capabilities: Optional[dict] = None,
    ):
        self._has_remote_subscription = has_remote_subscription
        self._has_electric = has_electric

        ToyotaVehicle.__init__(
            self,
            client,
            has_remote_subscription,
            has_electric,
            model_name,
            model_year,
            vin,
            region,
            generation,
            brand,
            backdoor_type,
            remote_capabilities,
            extended_capabilities,
        )
        self._last_vehicle_status = None
        self._last_graphql_status = None
        self._feature_timestamps = {}

    def inherit_state(self, previous: ToyotaVehicle) -> bool:
        """Carry cached responses and source timestamps into a new poll."""
        if not (
            isinstance(previous, SeventeenCYPlusToyotaVehicle)
            and super().inherit_state(previous)
        ):
            return False
        self._last_vehicle_status = previous._last_vehicle_status
        self._last_graphql_status = previous._last_graphql_status
        self._feature_timestamps = previous._feature_timestamps
        return True

    async def update(self):

        try:
            telemetry = await self._client.get_telemetry(
                self._vin,
                self._region,
                self.endpoint_generation,
            )
            if telemetry:
                self._parse_telemetry(telemetry)
        except Exception as e:
            _LOGGER.debug("Error fetching telemetry: %s", e)

        if self._has_remote_subscription:
            try:
                # Cached push data fills gaps. The polled source below wins when
                # neither response has timestamps.
                ws_handler = getattr(self._client, "_ws_handler", None)
                if ws_handler:
                    self.apply_graphql_status(
                        ws_handler.get_cached_status(self._vin)
                    )

                if self._generation == ApiVehicleGeneration.MM24:
                    vehicle_status = (
                        await self._client.graphql_get_vehicle_status(
                            self._vin,
                            self._backdoor_type,
                            self._region,
                        )
                    )
                    if vehicle_status:
                        self.apply_graphql_status(vehicle_status)
                    elif self._last_graphql_status:
                        self._parse_graphql_vehicle_status(
                            self._last_graphql_status
                        )
                else:
                    vehicle_status = (
                        await self._client.get_vehicle_status_17cyplus(
                            self._vin, self._region
                        )
                    )
                    if vehicle_status:
                        self._last_vehicle_status = vehicle_status
                        self._parse_vehicle_status(vehicle_status)
                    elif self._last_vehicle_status:
                        self._parse_vehicle_status(self._last_vehicle_status)
            except Exception as e:
                _LOGGER.debug("Error fetching vehicle status: %s", e)

            if self._generation != ApiVehicleGeneration.MM24:
                try:
                    previous_engine = self._features.get(VehicleFeatures.RemoteStartStatus)
                    engine_status = (
                        await self._client.get_engine_status_17cyplus(
                            self._vin, self._region
                        )
                    )
                    # A push received during this request is newer.
                    if engine_status and self._features.get(VehicleFeatures.RemoteStartStatus) is previous_engine:
                        self._parse_engine_status(engine_status)
                except Exception as e:
                    _LOGGER.debug("Error fetching engine status: %s", e)

        try:
            if (
                self._has_electric
                and self._generation != ApiVehicleGeneration.MM24
            ):
                electric_status = await self._client.get_electric_status(
                    self.vin, region=self._region
                )
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error parsing electric status: %s", e)

    async def poll_vehicle_refresh(self) -> None:
        """Instructs Toyota's systems to ping the vehicle to upload a fresh status."""
        errors = []
        refreshed = False

        if self._generation in (
            ApiVehicleGeneration.MM21,
            ApiVehicleGeneration.MM24,
        ):
            try:
                guid = await self._client.auth.get_guid()
                await self._client.graphql_pre_wake(guid, self._region)
            except Exception as e:
                errors.append(e)
                _LOGGER.debug("GraphQL pre-wake failed: %s", e)

            try:
                await self._client.graphql_confirm_subscription(
                    self._vin,
                    self._backdoor_type,
                    self._region,
                )
            except Exception as e:
                errors.append(e)
                _LOGGER.debug("GraphQL confirm subscription failed: %s", e)

            try:
                await self._client.graphql_refresh_status(
                    self._vin, self._region
                )
                refreshed = True
            except Exception as e:
                errors.append(e)
                _LOGGER.debug("GraphQL refresh status failed: %s", e)

        if self._generation in (
            ApiVehicleGeneration.CY17PLUS,
            ApiVehicleGeneration.MM21,
        ):
            try:
                await self._client.send_refresh_request_17cyplus(
                    self._vin, self._region
                )
                refreshed = True
            except Exception as e:
                errors.append(e)
                _LOGGER.debug("REST refresh request failed: %s", e)

        if not refreshed:
            if errors:
                raise errors[-1]
            raise RuntimeError(
                f"No refresh transport is available for {self.api_generation}."
            )

        try:
            if (
                self._has_electric
                and self._generation != ApiVehicleGeneration.MM24
            ):
                electric_status = await self._client.get_electric_realtime_status(
                    self.vin,
                    self.endpoint_generation,
                    self._region,
                )
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error refreshing electric status: %s", e)

    async def send_command(self, command: RemoteRequestCommand) -> None:
        """Send a generation-appropriate remote command."""
        command_name = self._command_map[command]
        if self._generation == ApiVehicleGeneration.MM24:
            await self._client.remote_request_24mm(
                self._vin, command_name, self._region
            )
            return
        await self._client.remote_request_17cyplus(
            self._vin, command_name, self._region
        )

    #
    # engine_status
    #

    def _parse_engine_status(self, engine_status: dict) -> None:
        if not engine_status or "status" not in engine_status:
            return

        running = normalize_engine_state(engine_status["status"])
        if running is None:
            return
        self._features[VehicleFeatures.RemoteStartStatus] = ToyotaRemoteStart(
            date=engine_status.get("date"),
            on=running,
            timer=engine_status.get("timer"),
        )
    
    #
    # electric_status
    #

    def _parse_electric_status(self, electric_status: dict) -> None:
        if not electric_status or "vehicleInfo" not in electric_status:
            return
        
        chargeInfo = electric_status["vehicleInfo"].get("chargeInfo", {})
        if not chargeInfo:
            return

        self._features[VehicleFeatures.ChargeDistance] = ToyotaNumeric(chargeInfo.get("evDistance"), chargeInfo.get("evDistanceUnit"))
        self._features[VehicleFeatures.ChargeDistanceAC] = ToyotaNumeric(chargeInfo.get("evDistanceAC"), chargeInfo.get("evDistanceUnit"))
        self._features[VehicleFeatures.ChargeLevel] = ToyotaNumeric(chargeInfo.get("chargeRemainingAmount"), "%")
        self._features[VehicleFeatures.PlugStatus] = ToyotaNumeric(chargeInfo.get("plugStatus"), "")
        self._features[VehicleFeatures.RemainingChargeTime] = ToyotaNumeric(chargeInfo.get("remainingChargeTime"), "")
        self._features[VehicleFeatures.EvTravelableDistance] = ToyotaNumeric(chargeInfo.get("evTravelableDistance"), "")
        self._features[VehicleFeatures.ChargeType] = ToyotaNumeric(chargeInfo.get("chargeType"), "")
        self._features[VehicleFeatures.ConnectorStatus] = ToyotaNumeric(chargeInfo.get("connectorStatus"), "")
        charging = normalize_charging_state(chargeInfo.get("plugStatus"))
        if charging is not None:
            self._features[VehicleFeatures.ChargingStatus] = ToyotaOpening(not charging)

    def _store_opening(self, feature, closed, locked, observed_at=None) -> bool:
        """Merge known opening state without converting missing values to false."""
        if closed is None and locked is None:
            return False
        current = self._features.get(feature)
        current_closed = current.closed if isinstance(current, ToyotaOpening) else None
        current_locked = (
            current.locked if isinstance(current, ToyotaLockableOpening) else None
        )

        def update_component(name, value, previous):
            if value is None:
                return previous
            timestamp = self._feature_timestamps.get((feature, name))
            if timestamp is not None and (
                observed_at is None or observed_at < timestamp
            ):
                return previous
            if observed_at is not None:
                self._feature_timestamps[(feature, name)] = observed_at
            return value

        closed = update_component("closed", closed, current_closed)
        locked = update_component("locked", locked, current_locked)
        if closed is None and locked is None:
            return False

        if locked is None:
            self._features[feature] = ToyotaOpening(closed=closed)
        else:
            self._features[feature] = ToyotaLockableOpening(
                closed=closed, locked=locked
            )
        return True

    def _store_numeric(self, feature, value, unit="", observed_at=None) -> bool:
        """Store a numeric value unless a newer observation already exists."""
        if value is None:
            return False
        timestamp = self._feature_timestamps.get((feature, "value"))
        if timestamp is not None and (
            observed_at is None or observed_at < timestamp
        ):
            return False
        if observed_at is not None:
            self._feature_timestamps[(feature, "value")] = observed_at
        self._features[feature] = ToyotaNumeric(value, unit)
        return True

    def _store_location(
        self, feature, latitude, longitude, observed_at=None
    ) -> bool:
        """Store a location unless a newer observation already exists."""
        if latitude is None or longitude is None:
            return False
        timestamp = self._feature_timestamps.get((feature, "location"))
        if timestamp is not None and (
            observed_at is None or observed_at < timestamp
        ):
            return False
        if observed_at is not None:
            self._feature_timestamps[(feature, "location")] = observed_at
        self._features[feature] = ToyotaLocation(latitude, longitude)
        return True

    def _store_remote_start(self, running, observed_at=None) -> bool:
        """Store engine state unless a newer observation already exists."""
        running = normalize_engine_state(running)
        if running is None:
            return False
        feature = VehicleFeatures.RemoteStartStatus
        timestamp = self._feature_timestamps.get((feature, "running"))
        if timestamp is not None and (
            observed_at is None or observed_at < timestamp
        ):
            return False
        if observed_at is not None:
            self._feature_timestamps[(feature, "running")] = observed_at
        self._features[feature] = ToyotaRemoteStart(
            date=None,
            on=running,
            timer=None,
        )
        return True

    def _parse_vehicle_status(self, vehicle_status: dict) -> None:
        if not vehicle_status:
            return

        observed_at = parse_api_timestamp(
            vehicle_status.get("occurrenceDate")
            or vehicle_status.get("occuranceDate")
        )
        if "latitude" in vehicle_status and "longitude" in vehicle_status:
            self._store_location(
                VehicleFeatures.ParkingLocation,
                vehicle_status["latitude"],
                vehicle_status["longitude"],
                observed_at,
            )

        categories = vehicle_status.get("vehicleStatus")
        if not categories:
            return

        for category in categories:
            if not category or "sections" not in category:
                continue
            for section in category["sections"]:
                if not section:
                    continue

                category_type = category.get("category")
                section_type = section.get("section")

                key = f"{category_type} {section_type}"

                feature = self._vehicle_status_category_map.get(key)
                if feature is None:
                    continue
                closed, locked = opening_state_from_values(
                    section.get("values", [])
                )
                self._store_opening(feature, closed, locked, observed_at)

    #
    # GraphQL vehicle status parser
    #

    _graphql_door_map = {
        "driverSide": VehicleFeatures.FrontDriverDoor,
        "passengerSide": VehicleFeatures.FrontPassengerDoor,
        "rearDriverSide": VehicleFeatures.RearDriverDoor,
        "rearPassengerSide": VehicleFeatures.RearPassengerDoor,
    }

    _graphql_window_map = {
        "driverSide": VehicleFeatures.FrontDriverWindow,
        "passengerSide": VehicleFeatures.FrontPassengerWindow,
        "rearDriverSide": VehicleFeatures.RearDriverWindow,
        "rearPassengerSide": VehicleFeatures.RearPassengerWindow,
    }

    _graphql_tire_map = {
        "frontLeft": VehicleFeatures.FrontDriverTire,
        "frontRight": VehicleFeatures.FrontPassengerTire,
        "rearLeft": VehicleFeatures.RearDriverTire,
        "rearRight": VehicleFeatures.RearPassengerTire,
        "spare": VehicleFeatures.SpareTirePressure,
    }

    def apply_graphql_status(self, status: dict) -> bool:
        """Apply a pushed AppSync status to this vehicle."""
        if not isinstance(status, dict):
            return False
        sections = {
            key: value if isinstance(value := status.get(key), dict) else {}
            for key in (
                "vehicleState",
                "location",
                "telemetry",
                "tripdetails",
                "electric",
            )
        }
        if not any(sections.values()):
            return False
        status = {**status, **sections}
        self._last_graphql_status = status
        self._parse_graphql_vehicle_status(status)
        return True

    def _parse_graphql_vehicle_status(self, status: dict) -> None:
        """Parse GraphQL GetVehicleStatus response into vehicle features."""
        if not status:
            return

        location = status.get("location")
        if location:
            self._store_location(
                VehicleFeatures.ParkingLocation,
                location.get("latitude"),
                location.get("longitude"),
                parse_api_timestamp(
                    location.get("lastUpdateDateTime")
                    or status.get("lastUpdateDateTime")
                ),
            )

        vehicle_state = status.get("vehicleState")
        if vehicle_state:
            observed_at = parse_api_timestamp(
                vehicle_state.get("lastUpdateDateTime")
                or status.get("lastUpdateDateTime")
            )

            # Doors (each has lock + position)
            doors = vehicle_state.get("doors")
            if doors:
                for door_key, feature in self._graphql_door_map.items():
                    door = doors.get(door_key)
                    if door:
                        closed, locked = opening_state_from_graphql(door)
                        self._store_opening(feature, closed, locked, observed_at)

            # Windows (position only)
            windows = vehicle_state.get("windows")
            if windows:
                for win_key, feature in self._graphql_window_map.items():
                    window = windows.get(win_key)
                    if window:
                        closed, _ = opening_state_from_graphql(window)
                        self._store_opening(feature, closed, None, observed_at)

            tires = vehicle_state.get("tires") or {}
            tire_observed_at = parse_api_timestamp(
                tires.get("lastUpdateDateTime")
                or vehicle_state.get("lastUpdateDateTime")
                or status.get("lastUpdateDateTime")
            )
            for tire_key, feature in self._graphql_tire_map.items():
                tire = tires.get(tire_key) or {}
                for pressure_key, default_unit in (
                    ("psi", "psi"),
                    ("kpa", "kPa"),
                    ("bar", "bar"),
                ):
                    pressure = tire.get(pressure_key)
                    if pressure is None:
                        continue
                    if isinstance(pressure, dict):
                        value = pressure.get("value")
                        unit = pressure.get("unit") or default_unit
                    else:
                        value = pressure
                        unit = default_unit
                    if self._store_numeric(
                        feature, value, unit, tire_observed_at
                    ):
                        break

            for opening_key in backdoor_candidates(self._backdoor_type):
                opening = vehicle_state.get(opening_key)
                if opening:
                    closed, locked = opening_state_from_graphql(opening)
                    if self._store_opening(
                        VehicleFeatures.Trunk, closed, locked, observed_at
                    ):
                        break

            # Hood (position only)
            hood = vehicle_state.get("hood")
            if hood:
                closed, _ = opening_state_from_graphql(hood)
                self._store_opening(
                    VehicleFeatures.Hood, closed, None, observed_at
                )

            # Moonroof (position only)
            moonroof = vehicle_state.get("moonroof")
            if moonroof:
                closed, _ = opening_state_from_graphql(moonroof)
                self._store_opening(
                    VehicleFeatures.Moonroof, closed, None, observed_at
                )

            # Engine
            engine = vehicle_state.get("engine")
            if engine:
                self._store_remote_start(
                    engine.get("running", engine.get("status")),
                    parse_api_timestamp(
                        engine.get("lastUpdateDateTime")
                        or vehicle_state.get("lastUpdateDateTime")
                        or status.get("lastUpdateDateTime")
                    ),
                )

        # Telemetry from GraphQL response
        telemetry = status.get("telemetry")
        if telemetry:
            telemetry_observed_at = parse_api_timestamp(
                telemetry.get("lastUpdateDateTime")
                or status.get("lastUpdateDateTime")
            )
            odo = telemetry.get("odo")
            if odo:
                self._store_numeric(
                    VehicleFeatures.Odometer,
                    odo.get("value"),
                    odo.get("unit", ""),
                    telemetry_observed_at,
                )
            fugage = telemetry.get("fugage")
            if fugage:
                self._store_numeric(
                    VehicleFeatures.FuelLevel,
                    fugage.get("value"),
                    fugage.get("unit", "%"),
                    telemetry_observed_at,
                )
            range_val = telemetry.get("range")
            if range_val:
                self._store_numeric(
                    VehicleFeatures.DistanceToEmpty,
                    range_val.get("value"),
                    range_val.get("unit", ""),
                    telemetry_observed_at,
                )

        trip_details = status.get("tripdetails") or {}
        trip_observed_at = parse_api_timestamp(
            trip_details.get("lastUpdateDateTime")
            or status.get("lastUpdateDateTime")
        )
        for key, feature in (
            ("tripA", VehicleFeatures.TripDetailsA),
            ("tripB", VehicleFeatures.TripDetailsB),
        ):
            trip = trip_details.get(key) or {}
            self._store_numeric(
                feature,
                trip.get("value"),
                trip.get("unit", ""),
                trip_observed_at,
            )

        self._parse_graphql_electric_status(status.get("electric"))

    def _parse_graphql_electric_status(self, electric: dict) -> None:
        """Parse the electric document returned for 24MM EVs and PHEVs."""
        if not electric:
            return

        observed_at = parse_api_timestamp(electric.get("lastUpdateDateTime"))
        battery = electric.get("battery") or {}
        charge_level = None
        for key in (
            "stateOfChargeDisplay",
            "plugInEnergy",
            "chargeRemainingAmount",
        ):
            measurement = battery.get(key)
            if measurement and measurement.get("value") is not None:
                charge_level = measurement
                break
        if charge_level:
            self._store_numeric(
                VehicleFeatures.ChargeLevel,
                charge_level.get("value"),
                charge_level.get("unit", "%"),
                observed_at,
            )

        electric_range = battery.get("travelableDistance") or {}
        if self._store_numeric(
            VehicleFeatures.ChargeDistance,
            electric_range.get("value"),
            electric_range.get("unit", ""),
            observed_at,
        ):
            self._store_numeric(
                VehicleFeatures.EvTravelableDistance,
                electric_range.get("value"),
                electric_range.get("unit", ""),
                observed_at,
            )

        electric_range_ac = battery.get("travelableDistanceAC") or {}
        self._store_numeric(
            VehicleFeatures.ChargeDistanceAC,
            electric_range_ac.get("value"),
            electric_range_ac.get("unit", ""),
            observed_at,
        )

        charging = electric.get("charging") or {}
        if not charging:
            return
        charging_observed_at = parse_api_timestamp(
            charging.get("lastUpdateDateTime")
        ) or observed_at

        self._store_numeric(
            VehicleFeatures.ChargeType,
            charging.get("chargeType"),
            observed_at=charging_observed_at,
        )
        remaining = charging.get("remainingChargeTime") or {}
        self._store_numeric(
            VehicleFeatures.RemainingChargeTime,
            remaining.get("value"),
            remaining.get("unit", ""),
            charging_observed_at,
        )

        connector = charging.get("connector") or {}
        self._store_numeric(
            VehicleFeatures.ConnectorStatus,
            connector.get("status"),
            observed_at=charging_observed_at,
        )
        plug_status = (
            connector.get("plugStatus")
            or connector.get("plugInInfo")
            or charging.get("chargingState")
        )
        self._store_numeric(
            VehicleFeatures.PlugStatus,
            plug_status,
            observed_at=charging_observed_at,
        )

        is_charging = normalize_charging_state(charging.get("chargingState"))
        if is_charging is None and not charging.get("chargingState"):
            is_charging = normalize_charging_state(charging.get("chargingStatus"))
        if is_charging is not None:
            self._store_opening(
                VehicleFeatures.ChargingStatus,
                closed=not is_charging,
                locked=None,
                observed_at=charging_observed_at,
            )

    #
    # get_telemetry
    #

    def _parse_telemetry(self, telemetry: dict) -> None:
        if not telemetry:
            return

        observed_at = parse_api_timestamp(telemetry.get("lastTimestamp"))
        tire_observed_at = parse_api_timestamp(telemetry.get("tirePressureTimestamp"))
        if observed_at is not None:
            self._features[VehicleFeatures.LastTimeStamp] = ToyotaNumeric(
                observed_at.timestamp(), ""
            )

        for key, value in telemetry.items():
            if value is None:
                continue

            if key == "lastTimestamp":
                continue

            if key == "tirePressureTimestamp":
                if tire_observed_at is not None:
                    self._store_numeric(
                        VehicleFeatures.LastTirePressureTimeStamp,
                        tire_observed_at.timestamp(),
                        observed_at=tire_observed_at,
                    )
                continue
                
            # fuel level is a primitive
            if key == "fuelLevel":
                self._store_numeric(
                    VehicleFeatures.FuelLevel,
                    value,
                    "%",
                    observed_at,
                )
                continue

            # Toyota labels telemetry vehicleLocation as Last Parked. It is
            # also the only location available on some accounts, so it backs
            # both location entities.
            if key == "vehicleLocation" and isinstance(value, dict):
                latitude = value.get("latitude")
                longitude = value.get("longitude")
                self._store_location(
                    VehicleFeatures.RealTimeLocation,
                    latitude,
                    longitude,
                    observed_at,
                )
                self._store_location(
                    VehicleFeatures.ParkingLocation,
                    latitude,
                    longitude,
                    observed_at,
                )
                continue

            if "Window" in key or "Roof" in key:
                if value not in (1, 2):
                    continue
                feature = self._vehicle_telemetry_map.get(key)
                if feature is not None:
                    self._store_opening(
                        feature, closed=(value == 2), locked=None, observed_at=observed_at
                    )
                continue

            if self._vehicle_telemetry_map.get(key) is not None:
                feature = self._vehicle_telemetry_map[key]
                feature_observed_at = observed_at
                if key.endswith("TirePressure") and tire_observed_at is not None:
                    feature_observed_at = tire_observed_at
                if isinstance(value, dict) and "value" in value:
                    self._store_numeric(
                        feature,
                        value["value"],
                        value.get("unit", ""),
                        feature_observed_at,
                    )
                else:
                    self._store_numeric(feature, value, observed_at=feature_observed_at)
                continue
