"""Fixture test for 24MM AppSync status parsing."""

from enum import Enum, auto
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/toyota_na"


class ApiVehicleGeneration(Enum):
    CY17PLUS = "17CYPLUS"
    MM21 = "21MM"
    MM24 = "24MM"


class RemoteRequestCommand(Enum):
    DoorLock = auto()
    DoorUnlock = auto()
    EngineStart = auto()
    EngineStop = auto()
    HazardsOn = auto()
    HazardsOff = auto()
    Refresh = auto()


class VehicleFeatures(Enum):
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
    ChargingStatus = auto()
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
    RemoteStartStatus = auto()
    RealTimeLocation = auto()
    ParkingLocation = auto()


class ToyotaVehicle:
    def __init__(
        self,
        client,
        has_remote_subscription,
        has_electric,
        model_name,
        model_year,
        vin,
        region,
        generation,
    ):
        self._client = client
        self._features = {}
        self._vin = vin
        self._region = region
        self._generation = generation


class ToyotaLocation:
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude


class ToyotaLockableOpening:
    def __init__(self, closed, locked):
        self.closed = closed
        self.locked = locked


class ToyotaNumeric:
    def __init__(self, value, unit):
        self.value = value
        self.unit = unit


class ToyotaOpening:
    def __init__(self, closed):
        self.closed = closed


class ToyotaRemoteStart:
    def __init__(self, date, on, timer):
        self.date = date
        self.on = on
        self.timer = timer


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


stubbed_module_names = [
    "toyota_na",
    "toyota_na.client",
    "toyota_na.vehicle",
    "toyota_na.vehicle.base_vehicle",
    "toyota_na.vehicle.entity_types",
    "toyota_na.vehicle.entity_types.ToyotaLocation",
    "toyota_na.vehicle.entity_types.ToyotaLockableOpening",
    "toyota_na.vehicle.entity_types.ToyotaNumeric",
    "toyota_na.vehicle.entity_types.ToyotaOpening",
    "toyota_na.vehicle.entity_types.ToyotaRemoteStart",
    "custom_components",
    "custom_components.toyota_na",
    "custom_components.toyota_na.vehicle_compat",
    "custom_components.toyota_na.patch_seventeen_cy_plus",
]
original_modules = {name: sys.modules.get(name) for name in stubbed_module_names}

_module("toyota_na")
_module("toyota_na.client", ToyotaOneClient=object)
_module("toyota_na.vehicle")
_module(
    "toyota_na.vehicle.base_vehicle",
    ApiVehicleGeneration=ApiVehicleGeneration,
    RemoteRequestCommand=RemoteRequestCommand,
    ToyotaVehicle=ToyotaVehicle,
    VehicleFeatures=VehicleFeatures,
)
_module("toyota_na.vehicle.entity_types")
for module_name, class_name, class_value in (
    ("ToyotaLocation", "ToyotaLocation", ToyotaLocation),
    ("ToyotaLockableOpening", "ToyotaLockableOpening", ToyotaLockableOpening),
    ("ToyotaNumeric", "ToyotaNumeric", ToyotaNumeric),
    ("ToyotaOpening", "ToyotaOpening", ToyotaOpening),
    ("ToyotaRemoteStart", "ToyotaRemoteStart", ToyotaRemoteStart),
):
    _module(
        "toyota_na.vehicle.entity_types." + module_name,
        **{class_name: class_value},
    )

custom_components = _module("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
component_package = _module("custom_components.toyota_na")
component_package.__path__ = [str(COMPONENT)]

compat_spec = importlib.util.spec_from_file_location(
    "custom_components.toyota_na.vehicle_compat",
    COMPONENT / "vehicle_compat.py",
)
compat_module = importlib.util.module_from_spec(compat_spec)
sys.modules[compat_spec.name] = compat_module
compat_spec.loader.exec_module(compat_module)

parser_spec = importlib.util.spec_from_file_location(
    "custom_components.toyota_na.patch_seventeen_cy_plus",
    COMPONENT / "patch_seventeen_cy_plus.py",
)
parser_module = importlib.util.module_from_spec(parser_spec)
sys.modules[parser_spec.name] = parser_module
parser_spec.loader.exec_module(parser_module)

for module_name, original_module in original_modules.items():
    if original_module is None:
        sys.modules.pop(module_name, None)
    else:
        sys.modules[module_name] = original_module


class TwentyFourMMStatusParserTests(unittest.TestCase):
    def test_parses_current_lock_aliases_and_electric_document(self):
        status = json.loads((ROOT / "tests/fixtures/vehicle_24mm.json").read_text())
        vehicle = parser_module.SeventeenCYPlusToyotaVehicle(
            client=object(),
            has_remote_subscription=True,
            has_electric=True,
            model_name="RAV4 Plug-in Hybrid",
            model_year="2026",
            vin="TESTVIN",
            region="US",
            generation=ApiVehicleGeneration.MM24,
        )

        vehicle._parse_graphql_vehicle_status(status)

        driver = vehicle._features[VehicleFeatures.FrontDriverDoor]
        passenger = vehicle._features[VehicleFeatures.FrontPassengerDoor]
        self.assertTrue(driver.closed)
        self.assertTrue(driver.locked)
        self.assertFalse(passenger.closed)
        self.assertFalse(passenger.locked)
        self.assertEqual(100, vehicle._features[VehicleFeatures.ChargeLevel].value)
        self.assertEqual(48, vehicle._features[VehicleFeatures.ChargeDistance].value)
        self.assertFalse(vehicle._features[VehicleFeatures.ChargingStatus].closed)


if __name__ == "__main__":
    unittest.main()
