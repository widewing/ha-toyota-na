"""Tests for the controllable remote-start entity."""

from enum import Enum, auto
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/toyota_na"


class VehicleFeatures(Enum):
    RemoteStartStatus = auto()


class ToyotaVehicle:
    pass


class ToyotaRemoteStart:
    def __init__(self, on=False):
        self.on = on
        self.end_time = "end"
        self.time_left = 7
        self.start_time = "start"
        self.timer = 10


class DataUpdateCoordinator:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


class ToyotaNABaseEntity:
    def __init__(self, coordinator, sensor_name, vin):
        self.coordinator = coordinator
        self.sensor_name = sensor_name
        self.vin = vin
        self.hass = None
        self.state_writes = 0

    @property
    def vehicle(self):
        return next(
            (vehicle for vehicle in self.coordinator.data if vehicle.vin == self.vin),
            None,
        )

    def feature(self, feature):
        if self.vehicle is None:
            return None
        return self.vehicle.features.get(feature)

    def async_write_ha_state(self):
        self.state_writes += 1


class SwitchEntity:
    pass


class SwitchDeviceClass:
    SWITCH = "switch"


class _Coordinator:
    def __init__(self, vehicles):
        self.data = vehicles
        self.refreshes = 0

    async def async_request_refresh(self):
        self.refreshes += 1


class _Vehicle:
    def __init__(self, vin="TESTVIN", subscribed=True, remote_start=None):
        self.vin = vin
        self.subscribed = subscribed
        self.features = {
            VehicleFeatures.RemoteStartStatus: remote_start or ToyotaRemoteStart()
        }
        self.commands = []
        self.polls = 0

    async def send_command(self, command):
        self.commands.append(command)

    async def poll_vehicle_refresh(self):
        self.polls += 1


class _Hass:
    def __init__(self):
        self.data = {}
        self.coroutines = []

    def async_create_task(self, coroutine):
        self.coroutines.append(coroutine)


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_switch_module():
    names = [
        "toyota_na",
        "toyota_na.vehicle",
        "toyota_na.vehicle.base_vehicle",
        "toyota_na.vehicle.entity_types",
        "toyota_na.vehicle.entity_types.ToyotaRemoteStart",
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.switch",
        "homeassistant.config_entries",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        "switch_test_package",
        "switch_test_package.base_entity",
        "switch_test_package.const",
        "switch_test_package.switch",
    ]
    originals = {name: sys.modules.get(name) for name in names}

    try:
        _module("toyota_na")
        _module("toyota_na.vehicle")
        _module(
            "toyota_na.vehicle.base_vehicle",
            ToyotaVehicle=ToyotaVehicle,
            VehicleFeatures=VehicleFeatures,
        )
        _module("toyota_na.vehicle.entity_types")
        _module(
            "toyota_na.vehicle.entity_types.ToyotaRemoteStart",
            ToyotaRemoteStart=ToyotaRemoteStart,
        )

        _module("homeassistant")
        _module("homeassistant.components")
        _module(
            "homeassistant.components.switch",
            SwitchDeviceClass=SwitchDeviceClass,
            SwitchEntity=SwitchEntity,
        )
        _module("homeassistant.config_entries", ConfigEntry=object)
        _module("homeassistant.core", HomeAssistant=object)
        _module("homeassistant.helpers")
        _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
        _module(
            "homeassistant.helpers.update_coordinator",
            DataUpdateCoordinator=DataUpdateCoordinator,
        )

        package = _module("switch_test_package")
        package.__path__ = [str(COMPONENT)]
        _module(
            "switch_test_package.base_entity",
            ToyotaNABaseEntity=ToyotaNABaseEntity,
        )
        _module(
            "switch_test_package.const",
            COMMAND_MAP={"engine_start": "start", "engine_stop": "stop"},
            DOMAIN="toyota_na",
            ENGINE_START="engine_start",
            ENGINE_STOP="engine_stop",
        )

        spec = importlib.util.spec_from_file_location(
            "switch_test_package.switch",
            COMPONENT / "switch.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


switch_module = _load_switch_module()


class RemoteStartSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_on_and_off_send_commands_and_refresh(self):
        vehicle = _Vehicle()
        coordinator = _Coordinator([vehicle])
        hass = _Hass()
        entity = switch_module.ToyotaRemoteStartSwitch(
            coordinator, "Remote Start", vehicle.vin
        )
        entity.hass = hass

        self.assertFalse(entity.is_on)
        await entity.async_turn_on()
        self.assertTrue(entity.is_on)
        self.assertEqual(["start"], vehicle.commands)

        with patch.object(switch_module.asyncio, "sleep", new=AsyncMock()):
            await hass.coroutines.pop()
        self.assertEqual(1, vehicle.polls)
        self.assertEqual(1, coordinator.refreshes)

        vehicle.features[VehicleFeatures.RemoteStartStatus].on = True
        await entity.async_turn_off()
        self.assertFalse(entity.is_on)
        self.assertEqual(["start", "stop"], vehicle.commands)

        vehicle.features[VehicleFeatures.RemoteStartStatus].on = False
        with patch.object(switch_module.asyncio, "sleep", new=AsyncMock()):
            await hass.coroutines.pop()
        self.assertFalse(entity.is_on)

    async def test_setup_only_creates_controls_for_subscribed_vehicles(self):
        subscribed = _Vehicle(vin="SUBSCRIBED", subscribed=True)
        unsubscribed = _Vehicle(vin="UNSUBSCRIBED", subscribed=False)
        coordinator = _Coordinator([subscribed, unsubscribed])
        hass = _Hass()
        hass.data = {
            "toyota_na": {"entry": {"coordinator": coordinator}},
        }
        config_entry = types.SimpleNamespace(entry_id="entry")
        added = []

        await switch_module.async_setup_entry(
            hass,
            config_entry,
            lambda entities, _update_before_add: added.extend(entities),
        )

        self.assertEqual(1, len(added))
        self.assertEqual("SUBSCRIBED", added[0].vin)

    async def test_command_failure_clears_optimistic_state(self):
        vehicle = _Vehicle()
        vehicle.send_command = AsyncMock(side_effect=RuntimeError("rejected"))
        coordinator = _Coordinator([vehicle])
        entity = switch_module.ToyotaRemoteStartSwitch(
            coordinator, "Remote Start", vehicle.vin
        )
        entity.hass = _Hass()

        with self.assertRaisesRegex(RuntimeError, "rejected"):
            await entity.async_turn_on()

        self.assertFalse(entity.is_on)
        self.assertEqual([], entity.hass.coroutines)

    def test_runtime_attributes_remain_available(self):
        vehicle = _Vehicle()
        entity = switch_module.ToyotaRemoteStartSwitch(
            _Coordinator([vehicle]), "Remote Start", vehicle.vin
        )

        self.assertEqual(
            {
                "end_time": "end",
                "minutes_remaining": 7,
                "start_time": "start",
                "total_runtime": 10,
            },
            entity.extra_state_attributes,
        )


if __name__ == "__main__":
    unittest.main()
