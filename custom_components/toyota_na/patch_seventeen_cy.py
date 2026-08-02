import datetime
import logging
from typing import Union

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
        )

    async def update(self):

        # Telemetry is parsed first, vehicle_status second, deliberately -- both report
        # window/moonroof state, and vehicle_status is the fresher/more authoritative source
        # for those when it includes them at all (confirmed by direct physical test on the
        # 17CYPLUS-class code path; same map/parsing pattern applies here). vehicle_status
        # running second means it overwrites telemetry's value when it has one, and leaves
        # telemetry's value in place on polls where vehicle_status doesn't report window state.
        try:
            # telemetry
            telemetry = await self._client.get_telemetry(self._vin, self._region, self._generation.value)
            if telemetry:
                self._parse_telemetry(telemetry)
        except Exception as e:
            _LOGGER.debug("Error parsing telemetry: %s", e)
            pass

        try:
            if self._has_remote_subscription:
                # vehicle_health_status
                vehicle_status = await self._client.get_vehicle_status(
                    self._vin, self._generation.value
                )
                if vehicle_status:
                    self._parse_vehicle_status(vehicle_status)
        except Exception as e:
            _LOGGER.debug("Error parsing vehicle status: %s", e)
            pass

        try:
            # engine_status
            engine_status = await self._client.get_engine_status(
                self._vin, self._generation.value
            )
            if engine_status:
                self._parse_engine_status(engine_status)
        except Exception as e:
            _LOGGER.debug("Error parsing engine status: %s", e)
            pass

        try:
            if self._has_electric:
                # electric_status
                electric_status = await self._client.get_electric_status(self.vin)
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error parsing electric status: %s", e)
            pass

    async def poll_vehicle_refresh(self) -> None:
        """Instructs Toyota's systems to ping the vehicle to upload a fresh status."""
        try:
            await self._client.send_refresh_status(self._vin, self._generation.value)
        except Exception as e:
            _LOGGER.warning("Vehicle refresh request failed: %s", e)

        """Tell Toyota to refresh electric status if applicable"""
        try:
            if self._has_electric:
                # electric_status
                electric_status = await self._client.get_electric_realtime_status(self.vin, self._generation.value)
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error refreshing electric status: %s", e)
            pass

    async def send_command(self, command: RemoteRequestCommand) -> None:
        """Start the engine. Periodically refreshes the vehicle status to determine if the engine is running."""
        await self._client.remote_request(
            self._vin,
            self._command_map[command],
            self._command_value_map[command],
            self._generation.value,
        )

    #
    # engine_status
    #

    def _parse_engine_status(self, engine_status: dict) -> None:
        if not engine_status or "status" not in engine_status:
            return

        self._features[VehicleFeatures.RemoteStartStatus] = ToyotaRemoteStart(
            date=engine_status.get("date"),
            on=engine_status["status"] == "1",
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
        self._features[VehicleFeatures.ChargingStatus] = ToyotaOpening(chargeInfo.get("connectorStatus") != 5)

    #
    # vehicle_health_status
    #

    # Position words mean the value reports open/closed state; lock words mean it reports
    # lock state instead. Some generations report only a single lock-state value with no
    # position at all, where older shapes report position first, then lock state. Reverse-
    # engineered from live payloads (see the identical constants/comment in
    # patch_seventeen_cy_plus.py), not from Toyota documentation.
    _POSITION_VALUES = ("closed", "open", "opened")
    _LOCK_STATE_VALUES = ("locked", "unlocked")

    def _isClosed(self, section) -> Union[bool, None]:
        """Whether the section reports a closed/open position. Returns None if position
        isn't reported at all (e.g. a single lock-state-only value)."""
        values = section.get("values", [])
        if not values:
            return False
        first_val = values[0].get("value", "").lower()
        if first_val in self._LOCK_STATE_VALUES:
            return None
        return first_val == "closed"

    def _isLocked(self, section) -> Union[bool, None]:
        """Whether the section reports lock state, as either the second value entry
        (older shape) or the only value entry (newer shape). Returns None if lock state
        isn't reported at all."""
        values = section.get("values", [])
        if not values:
            return None
        first_val = values[0].get("value", "").lower()
        if len(values) == 1 and first_val in self._LOCK_STATE_VALUES:
            return first_val == "locked"
        if len(values) >= 2:
            return values[1].get("value", "").lower() == "locked"
        return None

    def _parse_vehicle_status(self, vehicle_status: dict) -> None:
        if not vehicle_status:
            return

        # Real-time location is a one-off, so we'll just parse it out here
        if "latitude" in vehicle_status and "longitude" in vehicle_status:
            self._features[VehicleFeatures.ParkingLocation] = ToyotaLocation(
                vehicle_status["latitude"], vehicle_status["longitude"]
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

                # We don't support all features necessarily. So avoid throwing on a key error.
                if self._vehicle_status_category_map.get(key) is not None:
                    values = section.get("values", [])
                    if not values:
                        continue
                    first_val = values[0].get("value", "").lower()
                    # Deliberate: an unrecognized first value means skip this section for this
                    # poll, leaving any existing feature value from a prior poll in place (see
                    # the identical choice in patch_seventeen_cy_plus.py).
                    if first_val not in self._POSITION_VALUES + self._LOCK_STATE_VALUES:
                        continue

                    closed = self._isClosed(section)
                    locked = self._isLocked(section)

                    if locked is not None:
                        self._features[
                            self._vehicle_status_category_map[key]
                        ] = ToyotaLockableOpening(closed=closed, locked=locked)
                    elif closed is not None:
                        self._features[
                            self._vehicle_status_category_map[key]
                        ] = ToyotaOpening(closed=closed)

    #
    # get_telemetry
    #

    def _parse_telemetry(self, telemetry: dict) -> None:
        if not telemetry:
            return
            
        for key, value in telemetry.items():
            if value is None:
                continue

            # last time stamp is a primitive
            if key == "lastTimestamp":
                self._features[VehicleFeatures.LastTimeStamp] = ToyotaNumeric(datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp(), "")
                continue

            # tire pressure time stamp is a primitive
            if key == "tirePressureTimestamp":
                self._features[VehicleFeatures.LastTirePressureTimeStamp] = ToyotaNumeric(datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp(), "")
                continue

            # fuel level is a primitive
            if key == "fuelLevel":
                self._features[VehicleFeatures.FuelLevel] = ToyotaNumeric(value, "%")
                continue

            # vehicle_location has a different shape and different target entity class.
            # Toyota's own API labels this field "Last Parked", and it's the only location
            # telemetry provides, so it backs both RealTimeLocation and ParkingLocation
            # (the latter is otherwise only available via REST, which isn't always reachable).
            if key == "vehicleLocation":
                location = ToyotaLocation(value.get("latitude"), value.get("longitude"))
                self._features[VehicleFeatures.RealTimeLocation] = location
                self._features[VehicleFeatures.ParkingLocation] = location
                continue

            if self._vehicle_telemetry_map.get(key) is not None:
                if isinstance(value, dict) and "value" in value:
                    self._features[self._vehicle_telemetry_map[key]] = ToyotaNumeric(
                        value["value"], value.get("unit", "")
                    )
                else:
                    self._features[self._vehicle_telemetry_map[key]] = ToyotaNumeric(
                        value, ""
                    )
                continue
