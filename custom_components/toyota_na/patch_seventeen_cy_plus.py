import datetime
import logging

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

class SeventeenCYPlusToyotaVehicle(ToyotaVehicle):

    _has_remote_subscription = False
    _has_electric = False
    _last_vehicle_status = None  # persist last successful status across polls

    _command_map = {
        RemoteRequestCommand.DoorLock: "door-lock",
        RemoteRequestCommand.DoorUnlock: "door-unlock",
        RemoteRequestCommand.EngineStart: "engine-start",
        RemoteRequestCommand.EngineStop: "engine-stop",
        RemoteRequestCommand.HazardsOn: "hazard-on",
        RemoteRequestCommand.HazardsOff: "hazard-off",
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
        "vehicleLocation": VehicleFeatures.ParkingLocation,
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
            ApiVehicleGeneration.CY17PLUS,
        )

    _last_graphql_status = None  # persist last successful GraphQL status

    async def update(self):

        try:
            if self._has_remote_subscription:
                # REST v1/global/remote/status provides door/lock/window/hood/hatch
                vehicle_status = await self._client.get_vehicle_status_17cyplus(self._vin)
                if vehicle_status:
                    self._last_vehicle_status = vehicle_status
                    self._parse_vehicle_status(vehicle_status)
                elif self._last_vehicle_status:
                    self._parse_vehicle_status(self._last_vehicle_status)

                # WebSocket cached data (if available) provides additional detail
                ws_handler = getattr(self._client, '_ws_handler', None)
                if ws_handler:
                    ws_status = ws_handler.get_cached_status(self._vin)
                    if ws_status and ws_status.get("vehicleState"):
                        self._last_graphql_status = ws_status
                        self._parse_graphql_vehicle_status(ws_status)
        except Exception as e:
            _LOGGER.debug("Error fetching vehicle status: %s", e)
            pass

        try:
            # telemetry
            telemetry = await self._client.get_telemetry(self._vin, self._region)
            if telemetry:
                self._parse_telemetry(telemetry)
        except Exception as e:
            _LOGGER.debug("Error fetching telemetry: %s", e)
            pass

        try:
            if self._has_remote_subscription:
                # engine_status - use 17cyplus endpoint
                engine_status = await self._client.get_engine_status_17cyplus(self._vin)
                if engine_status:
                    _LOGGER.debug("Engine status received for VIN %s", self._vin[-4:])
                    self._parse_engine_status(engine_status)
                else:
                    _LOGGER.debug("Engine status returned None for VIN %s", self._vin[-4:])
        except Exception as e:
            _LOGGER.debug("Error fetching engine status: %s", e)
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
        # GraphQL refresh flow: pre-wake -> confirm subscription -> refresh
        try:
            guid = await self._client.auth.get_guid()
            await self._client.graphql_pre_wake(guid)
        except Exception as e:
            _LOGGER.debug("GraphQL pre-wake failed: %s", e)

        try:
            await self._client.graphql_confirm_subscription(self._vin)
        except Exception as e:
            _LOGGER.debug("GraphQL confirm subscription failed: %s", e)

        try:
            await self._client.graphql_refresh_status(self._vin)
        except Exception as e:
            _LOGGER.debug("GraphQL refresh status failed: %s", e)

        # Also do REST refresh
        try:
            await self._client.send_refresh_request_17cyplus(self._vin)
        except Exception as e:
            _LOGGER.debug("REST refresh request failed: %s", e)

        try:
            if self._has_electric:
                electric_status = await self._client.get_electric_realtime_status(self.vin)
                if electric_status:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.debug("Error refreshing electric status: %s", e)
            pass

    async def send_command(self, command: RemoteRequestCommand) -> None:
        """Start the engine. Periodically refreshes the vehicle status to determine if the engine is running."""
        await self._client.remote_request_17cyplus(self._vin, self._command_map[command])

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

    def _isClosed(self, section) -> bool:
        values = section.get("values", [])
        if not values:
            return False
        return values[0].get("value", "").lower() == "closed"

    def _isLocked(self, section) -> bool:
        values = section.get("values", [])
        if len(values) < 2:
            return False
        return values[1].get("value", "").lower() == "locked"

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
                    # CLOSED is always the first value entry. So we can use it to determine which subtype to instantiate
                    if len(values) == 1:
                        self._features[
                            self._vehicle_status_category_map[key]
                        ] = ToyotaOpening(self._isClosed(section))
                    elif len(values) >= 2:
                        self._features[
                            self._vehicle_status_category_map[key]
                        ] = ToyotaLockableOpening(
                            closed=self._isClosed(section),
                            locked=self._isLocked(section),
                        )

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

    def _parse_graphql_vehicle_status(self, status: dict) -> None:
        """Parse GraphQL GetVehicleStatus response into vehicle features."""
        if not status:
            return

        # Location
        location = status.get("location")
        if location and location.get("latitude") and location.get("longitude"):
            self._features[VehicleFeatures.ParkingLocation] = ToyotaLocation(
                location["latitude"], location["longitude"]
            )

        vehicle_state = status.get("vehicleState")
        if not vehicle_state:
            return

        # Doors (each has lock + position)
        doors = vehicle_state.get("doors")
        if doors:
            for door_key, feature in self._graphql_door_map.items():
                door = doors.get(door_key)
                if door:
                    lock_status = (door.get("lock") or {}).get("status", "").lower()
                    pos_status = (door.get("position") or {}).get("status", "").lower()
                    self._features[feature] = ToyotaLockableOpening(
                        closed=(pos_status == "closed"),
                        locked=(lock_status == "locked"),
                    )

        # Windows (position only)
        windows = vehicle_state.get("windows")
        if windows:
            for win_key, feature in self._graphql_window_map.items():
                window = windows.get(win_key)
                if window:
                    pos_status = ((window.get("position") or {}).get("status", "")).lower()
                    self._features[feature] = ToyotaOpening(closed=(pos_status == "closed"))

        # Hatch / Trunk / Tailgate -> mapped to VehicleFeatures.Trunk
        for opening_key in ("hatch", "trunk", "tailgate"):
            opening = vehicle_state.get(opening_key)
            if opening:
                lock_obj = opening.get("lock")
                pos_obj = opening.get("position")
                if lock_obj or pos_obj:
                    lock_status = ((lock_obj or {}).get("status", "")).lower()
                    pos_status = ((pos_obj or {}).get("status", "")).lower()
                    if lock_obj:
                        self._features[VehicleFeatures.Trunk] = ToyotaLockableOpening(
                            closed=(pos_status == "closed"),
                            locked=(lock_status == "locked"),
                        )
                    else:
                        self._features[VehicleFeatures.Trunk] = ToyotaOpening(
                            closed=(pos_status == "closed")
                        )
                    break  # use first available

        # Hood (position only)
        hood = vehicle_state.get("hood")
        if hood:
            pos_status = ((hood.get("position") or {}).get("status", "")).lower()
            self._features[VehicleFeatures.Hood] = ToyotaOpening(closed=(pos_status == "closed"))

        # Moonroof (position only)
        moonroof = vehicle_state.get("moonroof")
        if moonroof:
            pos_status = ((moonroof.get("position") or {}).get("status", "")).lower()
            self._features[VehicleFeatures.Moonroof] = ToyotaOpening(closed=(pos_status == "closed"))

        # Engine
        engine = vehicle_state.get("engine")
        if engine:
            running = engine.get("running")
            if running is not None:
                self._features[VehicleFeatures.RemoteStartStatus] = ToyotaRemoteStart(
                    date=None,
                    on=bool(running),
                    timer=None,
                )

        # Telemetry from GraphQL response
        telemetry = status.get("telemetry")
        if telemetry:
            odo = telemetry.get("odo")
            if odo and odo.get("value") is not None:
                self._features[VehicleFeatures.Odometer] = ToyotaNumeric(
                    odo["value"], odo.get("unit", "")
                )
            fugage = telemetry.get("fugage")
            if fugage and fugage.get("value") is not None:
                self._features[VehicleFeatures.FuelLevel] = ToyotaNumeric(
                    fugage["value"], fugage.get("unit", "%")
                )
            range_val = telemetry.get("range")
            if range_val and range_val.get("value") is not None:
                self._features[VehicleFeatures.DistanceToEmpty] = ToyotaNumeric(
                    range_val["value"], range_val.get("unit", "")
                )

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

            # vehicle_location has a different shape and different target entity class
            if key == "vehicleLocation":
                self._features[VehicleFeatures.RealTimeLocation] = ToyotaLocation(
                    value.get("latitude"), value.get("longitude")
                )
                continue

            if "Window" in key or "Roof" in key:
                self._features[
                    self._vehicle_telemetry_map.get(key, key)
                ] = ToyotaOpening(closed=(value == 2))
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
