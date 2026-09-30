from abc import ABC, abstractmethod
from enum import Enum, auto, unique
from typing import Optional, Union

from toyota_na.client import ToyotaOneClient
from toyota_na.vehicle.entity_types.ToyotaLocation import ToyotaLocation
from toyota_na.vehicle.entity_types.ToyotaLockableOpening import ToyotaLockableOpening
from toyota_na.vehicle.entity_types.ToyotaNumeric import ToyotaNumeric
from toyota_na.vehicle.entity_types.ToyotaOpening import ToyotaOpening
from toyota_na.vehicle.entity_types.ToyotaRemoteStart import ToyotaRemoteStart

from .vehicle_helpers import endpoint_generation, first_capability


@unique
class ApiVehicleGeneration(Enum):
    CY17 = "17CY"
    CY17PLUS = "17CYPLUS"
    MM21 = "21MM"
    MM24 = "24MM"
    NG86 = "GR86"
    PRE17CY = "PRE17CY"


@unique
class VehicleFeatures(Enum):
    # Doors/Windows
    FrontDriverDoor = auto()
    FrontDriverWindow = auto()
    FrontPassengerDoor = auto()
    FrontPassengerWindow = auto()
    RearDriverDoor = auto()
    RearDriverWindow = auto()
    RearPassengerDoor = auto()
    RearPassengerWindow = auto()
    Trunk = auto()
    Moonroof = auto()
    Hood = auto()

    # Charging Status
    ChargingStatus = auto()
    
    # Numeric values
    DistanceToEmpty = auto()
    FrontDriverTire = auto()
    FrontPassengerTire = auto()
    RearDriverTire = auto()
    RearPassengerTire = auto()
    SpareTirePressure = auto()
    FuelLevel = auto()
    ChargeDistance = auto()
    ChargeDistanceAC = auto()
    ChargeLevel = auto()
    Odometer = auto()
    TripDetailsA = auto()
    TripDetailsB = auto()
    NextService = auto()
    LastTimeStamp = auto()
    LastTirePressureTimeStamp = auto()
    Speed = auto()
    PlugStatus = auto()
    RemainingChargeTime = auto()
    EvTravelableDistance = auto()
    ChargeType = auto()
    ConnectorStatus = auto()

    #Times
    OccurrenceDate = auto()

    # Engine status
    RemoteStartStatus = auto()

    # Location
    RealTimeLocation = auto()
    ParkingLocation = auto()


@unique
class RemoteRequestCommand(Enum):
    DoorLock = auto()
    DoorUnlock = auto()
    EngineStart = auto()
    EngineStop = auto()
    HazardsOn = auto()
    HazardsOff = auto()
    VehicleFinder = auto()
    Refresh = auto()


class ToyotaVehicle(ABC):
    """Vehicle control and metadata object."""

    _client: ToyotaOneClient
    _features: dict[
        VehicleFeatures,
        Union[
            ToyotaLocation,
            ToyotaLockableOpening,
            ToyotaNumeric,
            ToyotaRemoteStart,
            ToyotaOpening,
        ],
    ]
    _has_remote_subscription = False
    _has_electric = False
    _model_name: str
    _model_year: str
    _generation: ApiVehicleGeneration
    _vin: str
    _region: str
    _command_map: dict[RemoteRequestCommand, str] = {}

    _COMMAND_CAPABILITIES = {
        RemoteRequestCommand.DoorLock: (
            "dlockUnlockCapable",
            "doorLockUnlockCapable",
        ),
        RemoteRequestCommand.DoorUnlock: (
            "dlockUnlockCapable",
            "doorLockUnlockCapable",
        ),
        RemoteRequestCommand.EngineStart: (
            "estartEnabled",
            "estartStopCapable",
            "remoteEngineStartStop",
        ),
        RemoteRequestCommand.EngineStop: (
            "estopEnabled",
            "estartStopCapable",
            "remoteEngineStartStop",
        ),
        RemoteRequestCommand.HazardsOn: ("hazardCapable",),
        RemoteRequestCommand.HazardsOff: ("hazardCapable",),
        RemoteRequestCommand.VehicleFinder: (
            "vehicleFinderCapable",
            "vehicleFinder",
        ),
    }
    _COMMANDS_REQUIRING_EXPLICIT_CAPABILITY = {
        RemoteRequestCommand.VehicleFinder,
    }

    def __init__(
        self,
        client: ToyotaOneClient,
        has_remote_subscription,
        has_electric,
        model_name: str,
        model_year: str,
        vin: str,
        region: str,
        generation: ApiVehicleGeneration,
        brand: str = "T",
        backdoor_type: Optional[str] = None,
        remote_capabilities: Optional[dict] = None,
        extended_capabilities: Optional[dict] = None,
    ):
        """
        Initialize a new vehicle object. Must call `vehicle.update()` to fully populate the object.

        :param vin: Vehicle identification number
        """

        self._features = {}
        self._client = client
        self._generation = generation
        self._has_remote_subscription = has_remote_subscription
        self._has_electric = has_electric
        self._model_name = model_name
        self._model_year = model_year
        self._vin = vin
        self._region = region
        self._brand = brand
        self._backdoor_type = backdoor_type
        self._remote_capabilities = remote_capabilities or {}
        self._extended_capabilities = extended_capabilities or {}

    @abstractmethod
    async def poll_vehicle_refresh(self) -> None:
        """Instructs Toyota's systems to ping the vehicle to upload a fresh status. Useful when certain actions have been taken, such as locking or unlocking doors."""
        pass

    @abstractmethod
    async def send_command(self, command: RemoteRequestCommand) -> None:
        """Start the engine. Periodically refreshes the vehicle status to determine if the engine is running."""
        pass

    @abstractmethod
    async def update(self):
        """Calls the required Toyota APIs and instantiates all the attributes."""
        pass

    @property
    def features(
        self,
    ) -> dict[
        VehicleFeatures,
        Union[
            ToyotaLocation,
            ToyotaLockableOpening,
            ToyotaNumeric,
            ToyotaOpening,
            ToyotaRemoteStart,
        ],
    ]:
        """Provides a programmatic representation of all the features of the vehicle and their current states."""
        return self._features

    # We only very sparingly expose direct properties. Most vehicle atrributes should be added to the features dictionary.
    @property
    def generation(self):
        return self._generation

    @property
    def endpoint_generation(self):
        return endpoint_generation(self._generation.value)

    @property
    def model_name(self):
        return self._model_name

    @property
    def model_year(self):
        return self._model_year

    @property
    def subscribed(self):
        return self._has_remote_subscription
    
    @property
    def electric(self):
        return self._has_electric

    @property
    def brand(self):
        return self._brand

    @property
    def region(self):
        return self._region

    @property
    def backdoor_type(self):
        return self._backdoor_type

    @property
    def remote_capabilities(self):
        return self._remote_capabilities

    @property
    def capabilities(self):
        """Compatibility alias for remote service capabilities."""
        return self._remote_capabilities

    @property
    def extended_capabilities(self):
        return self._extended_capabilities

    @property
    def api_generation(self):
        """Return the generation string reported by vehicle discovery."""
        return self._generation.value

    def supports_command(self, command: RemoteRequestCommand) -> bool:
        """Return whether the API transport and vehicle support a command."""
        if command not in self._command_map:
            return False

        keys = self._COMMAND_CAPABILITIES.get(command)
        if keys is None:
            return True
        supported = first_capability(
            self._remote_capabilities,
            self._extended_capabilities,
            keys,
        )
        if command in self._COMMANDS_REQUIRING_EXPLICIT_CAPABILITY:
            return supported is True
        return supported is not False

    def inherit_state(self, previous: "ToyotaVehicle") -> bool:
        """Share observations with matching vehicle instances used by active polls."""
        if (
            previous.vin != self.vin
            or previous.generation != self.generation
            or previous.region != self.region
            or previous.subscribed != self.subscribed
            or previous.electric != self.electric
        ):
            return False
        self._features = previous.features
        return True

    @property
    def vin(self):
        return self._vin

    def __repr__(self):
        str = f"{self.__class__.__name__}(\n    features=(\n"
        for key, value in self._features.items():
            str += f"       {key}={value}\n"
        return f"{str}  )\n)"
