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
    }

    def __init__(
        self,
        client: ToyotaOneClient,
        has_remote_subscription: bool,
        has_electric: bool,
        model_name: str,
        model_year: str,
        vin: str,
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
            ApiVehicleGeneration.CY17,
        )

    async def update(self):
        
        try:
            if self._has_remote_subscription:
                # vehicle_health_status
                vehicle_status = await self._client.get_vehicle_status(
                    self._vin, self._generation.value
                )
                self._parse_vehicle_status(vehicle_status)
        except Exception as e:
            _LOGGER.error(e)
            pass

        try:
            # telemetry
            telemetry = await self._client.get_telemetry(self._vin, self._generation.value)
            self._parse_telemetry(telemetry)
        except Exception as e:
            _LOGGER.error(e)
            pass

        try:
            # engine_status
            engine_status = await self._client.get_engine_status(
                self._vin, self._generation.value
            )
            self._parse_engine_status(engine_status)
        except Exception as e:
            _LOGGER.error(e)
            pass

        try:
            if self._has_electric:
                # electric_status
                electric_status = await self._client.get_electric_status(self.vin)
                if electric_status is not None:
                    self._parse_electric_status(electric_status)
        except Exception as e:
            _LOGGER.error(e)
            pass

    async def poll_vehicle_refresh(self) -> None:
        """Instructs Toyota's systems to ping the vehicle to upload a fresh status. Useful when certain actions have been taken, such as locking or unlocking doors."""
        await self._client.send_refresh_status(self._vin, self._generation.value)

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

        self._features[VehicleFeatures.RemoteStartStatus] = ToyotaRemoteStart(
            date=engine_status.get("date"),
            on=engine_status["status"] == "1",
            timer=engine_status.get("timer"),
        )

    #
    # electric_status
    #

    def _parse_electric_status(self, electric_status: dict) -> None:
        self._features[VehicleFeatures.ChargeDistance] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["evDistance"], electric_status["vehicleInfo"]["chargeInfo"]["evDistanceUnit"])
        self._features[VehicleFeatures.ChargeDistanceAC] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["evDistanceAC"], electric_status["vehicleInfo"]["chargeInfo"]["evDistanceUnit"])
        self._features[VehicleFeatures.ChargeLevel] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["chargeRemainingAmount"], "%")
        self._features[VehicleFeatures.PlugStatus] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["plugStatus"], "")
        self._features[VehicleFeatures.RemainingChargeTime] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["remainingChargeTime"], "")
        self._features[VehicleFeatures.EvTravelableDistance] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["evTravelableDistance"], "")
        self._features[VehicleFeatures.ChargeType] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["chargeType"], "")
        self._features[VehicleFeatures.ConnectorStatus] = ToyotaNumeric(electric_status["vehicleInfo"]["chargeInfo"]["connectorStatus"], "")
        self._features[VehicleFeatures.ChargingStatus] = ToyotaOpening(electric_status["vehicleInfo"]["chargeInfo"]["connectorStatus"] != 5)

    #
    # vehicle_health_status
    #

    def _isClosed(self, section) -> bool:
        return section["values"][0]["value"].lower() == "closed"

    def _isLocked(self, section) -> bool:
        return section["values"][1]["value"].lower() == "locked"

    def _parse_vehicle_status(self, vehicle_status: dict) -> None:

        # Real-time location is a one-off, so we'll just parse it out here
        if "latitude" in vehicle_status and "longitude" in vehicle_status:
            self._features[VehicleFeatures.ParkingLocation] = ToyotaLocation(
                vehicle_status["latitude"], vehicle_status["longitude"]
            )

        for category in vehicle_status["vehicleStatus"]:
            for section in category["sections"]:

                category_type = category["category"]
                section_type = section["section"]

                key = f"{category_type} {section_type}"

                # We don't support all features necessarily. So avoid throwing on a key error.
                if self._vehicle_status_category_map.get(key) is not None:

                    # CLOSED is always the first value entry. So we can use it to determine which subtype to instantiate
                    if section["values"].__len__() == 1:
                        self._features[
                            self._vehicle_status_category_map[key]
                        ] = ToyotaOpening(self._isClosed(section))
                    else:
                        self._features[
                            self._vehicle_status_category_map[key]
                        ] = ToyotaLockableOpening(
                            closed=self._isClosed(section),
                            locked=self._isLocked(section),
                        )

    #
    # get_telemetry
    #

    def _parse_telemetry(self, telemetry: dict) -> None:
        for key, value in telemetry.items():
            
            # last time stamp is a primitive
            if key == "lastTimestamp" and value is not None:
                self._features[VehicleFeatures.LastTimeStamp] = ToyotaNumeric(datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp(), "")
                continue

            # tire pressure time stamp is a primitive
            if key == "tirePressureTimestamp" and value is not None:
                self._features[VehicleFeatures.LastTirePressureTimeStamp] = ToyotaNumeric(datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp(), "")
                continue

            # fuel level is a primitive
            if key == "fuelLevel" and value is not None:
                self._features[VehicleFeatures.FuelLevel] = ToyotaNumeric(value, "%")
                continue

            # vehicle_location has a different shape and different target entity class
            if key == "vehicleLocation" and value is not None:
                self._features[VehicleFeatures.RealTimeLocation] = ToyotaLocation(
                    value["latitude"], value["longitude"]
                )
                continue

            if self._vehicle_telemetry_map.get(key) is not None and value is not None:
                self._features[self._vehicle_telemetry_map[key]] = ToyotaNumeric(
                    value["value"], value["unit"]
                )
                continue