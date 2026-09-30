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
    normalize_charging_state,
    normalize_engine_state,
    opening_state_from_values,
    parse_api_timestamp,
)

_LOGGER = logging.getLogger(__name__)

class SeventeenCYToyotaVehicle(ToyotaVehicle):

    _has_remote_subscription = False
    _has_electric = False

    _command_map = {
        RemoteRequestCommand.DoorLock: "DL",
        RemoteRequestCommand.DoorUnlock: "DL",
        RemoteRequestCommand.EngineStart: "RES",
        RemoteRequestCommand.EngineStop: "RES",
        RemoteRequestCommand.HazardsOn: "HZ",
        RemoteRequestCommand.HazardsOff: "HZ",
        RemoteRequestCommand.Refresh: "refresh",
    }

    _command_value_map = {
        RemoteRequestCommand.DoorLock: 1,
        RemoteRequestCommand.DoorUnlock: 2,
        RemoteRequestCommand.EngineStart: 1,
        RemoteRequestCommand.EngineStop: 2,
        RemoteRequestCommand.HazardsOn: 1,
        RemoteRequestCommand.HazardsOff: 2,
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
            ApiVehicleGeneration.CY17,
            brand,
            backdoor_type,
            remote_capabilities,
            extended_capabilities,
        )
        self._feature_timestamps = {}

    def inherit_state(self, previous: ToyotaVehicle) -> bool:
        """Carry source timestamps into a new coordinator poll."""
        if not (
            isinstance(previous, SeventeenCYToyotaVehicle)
            and super().inherit_state(previous)
        ):
            return False
        self._feature_timestamps = previous._feature_timestamps
        return True

    async def update(self):
        
        try:
            if self._has_remote_subscription:
                # vehicle_health_status
                vehicle_status = await self._client.get_vehicle_status_17cy(
                    self._vin, self._region
                )
                if vehicle_status:
                    self._parse_vehicle_status(vehicle_status)
        except Exception as e:
            _LOGGER.debug("Error parsing vehicle status: %s", e)
            pass

        try:
            # telemetry
            telemetry = await self._client.get_telemetry(
                self._vin,
                self._region,
                self.endpoint_generation,
            )
            if telemetry:
                self._parse_telemetry(telemetry)
        except Exception as e:
            _LOGGER.debug("Error parsing telemetry: %s", e)
            pass

        try:
            # engine_status
            engine_status = await self._client.get_engine_status_17cy(
                self._vin, self._region
            )
            if engine_status:
                self._parse_engine_status(engine_status)
        except Exception as e:
            _LOGGER.debug("Error parsing engine status: %s", e)
            pass

        try:
            if self._has_electric:
                # electric_status
                electric_status = await self._client.get_electric_status(
                    self.vin, region=self._region
                )
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error parsing electric status: %s", e)
            pass

    async def poll_vehicle_refresh(self) -> None:
        """Instructs Toyota's systems to ping the vehicle to upload a fresh status."""
        await self._client.send_refresh_request_17cy(
            self._vin, self._region
        )

        """Tell Toyota to refresh electric status if applicable"""
        try:
            if self._has_electric:
                # electric_status
                electric_status = await self._client.get_electric_realtime_status(
                    self.vin,
                    self.endpoint_generation,
                    self._region,
                )
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error refreshing electric status: %s", e)
            pass

    async def send_command(self, command: RemoteRequestCommand) -> None:
        """Start the engine. Periodically refreshes the vehicle status to determine if the engine is running."""
        await self._client.remote_request_17cy(
            self._vin,
            self._command_map[command],
            self._command_value_map[command],
            self._region,
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

    #
    # vehicle_health_status
    #

    def _store_opening(self, feature, closed, locked, observed_at=None) -> None:
        """Merge known opening state without guessing from missing values."""
        if closed is None and locked is None:
            return
        current = self._features.get(feature)
        current_closed = current.closed if isinstance(current, ToyotaOpening) else None
        current_locked = (
            current.locked if isinstance(current, ToyotaLockableOpening) else None
        )

        def merge_component(name, value, previous):
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

        closed = merge_component("closed", closed, current_closed)
        locked = merge_component("locked", locked, current_locked)
        if locked is None:
            self._features[feature] = ToyotaOpening(closed=closed)
        else:
            self._features[feature] = ToyotaLockableOpening(
                closed=closed,
                locked=locked,
            )

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

        if "vehicleStatus" not in vehicle_status or vehicle_status["vehicleStatus"] is None:
            return

        for category in vehicle_status["vehicleStatus"]:
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

            # tire pressure time stamp is a primitive
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
