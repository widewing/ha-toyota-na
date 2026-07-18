"""Tests for voice-compatible window, horn, and buzzer controls."""

from enum import Enum, IntFlag, auto
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/toyota_na"


class VehicleFeatures(Enum):
    FrontDriverWindow = auto()
    FrontPassengerWindow = auto()
    RearDriverWindow = auto()
    RearPassengerWindow = auto()


class ToyotaVehicle:
    pass


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


class CoverEntity:
    pass


class CoverDeviceClass:
    WINDOW = "window"


class CoverEntityFeature(IntFlag):
    OPEN = auto()
    CLOSE = auto()


class ButtonEntity:
    pass


class ButtonDeviceClass:
    IDENTIFY = "identify"


class _Opening:
    def __init__(self, closed=True):
        self.closed = closed


class _Vehicle:
    def __init__(self, vin="TESTVIN", generation="24MM", subscribed=True):
        self.vin = vin
        self.generation = generation
        self.subscribed = subscribed
        self.features = {
            feature: _Opening() for feature in VehicleFeatures
        }
        self.commands = []
        self.polls = 0

    async def send_command(self, command):
        self.commands.append(command)

    async def poll_vehicle_refresh(self):
        self.polls += 1


class _Coordinator:
    def __init__(self, vehicles):
        self.data = vehicles
        self.refreshes = 0

    async def async_request_refresh(self):
        self.refreshes += 1


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


def _load_platform(filename, platform_name, platform_attributes, const_attributes):
    package_name = f"voice_control_test_{filename}"
    names = [
        "toyota_na",
        "toyota_na.vehicle",
        "toyota_na.vehicle.base_vehicle",
        "homeassistant",
        "homeassistant.components",
        f"homeassistant.components.{platform_name}",
        "homeassistant.config_entries",
        "homeassistant.core",
        "homeassistant.helpers",
        "homeassistant.helpers.entity_platform",
        "homeassistant.helpers.update_coordinator",
        package_name,
        f"{package_name}.base_entity",
        f"{package_name}.const",
        f"{package_name}.{filename}",
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
        _module("homeassistant")
        _module("homeassistant.components")
        _module(
            f"homeassistant.components.{platform_name}",
            **platform_attributes,
        )
        _module("homeassistant.config_entries", ConfigEntry=object)
        _module("homeassistant.core", HomeAssistant=object)
        _module("homeassistant.helpers")
        _module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
        _module(
            "homeassistant.helpers.update_coordinator",
            DataUpdateCoordinator=DataUpdateCoordinator,
        )

        package = _module(package_name)
        package.__path__ = [str(COMPONENT)]
        _module(f"{package_name}.base_entity", ToyotaNABaseEntity=ToyotaNABaseEntity)
        _module(f"{package_name}.const", **const_attributes)

        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{filename}",
            COMPONENT / f"{filename}.py",
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


cover_module = _load_platform(
    "cover",
    "cover",
    {
        "CoverDeviceClass": CoverDeviceClass,
        "CoverEntity": CoverEntity,
        "CoverEntityFeature": CoverEntityFeature,
    },
    {
        "COMMAND_MAP": {"windows_open": "open", "windows_close": "close"},
        "DOMAIN": "toyota_na",
        "WINDOWS_CLOSE": "windows_close",
        "WINDOWS_OPEN": "windows_open",
    },
)

button_module = _load_platform(
    "button",
    "button",
    {
        "ButtonDeviceClass": ButtonDeviceClass,
        "ButtonEntity": ButtonEntity,
    },
    {
        "BUZZER_WARNING": "buzzer_warning",
        "COMMAND_MAP": {
            "sound_horn": "horn",
            "buzzer_warning": "buzzer",
        },
        "DOMAIN": "toyota_na",
        "SOUND_HORN": "sound_horn",
    },
)


class VoiceRemoteControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_window_cover_opens_closes_and_refreshes(self):
        vehicle = _Vehicle()
        coordinator = _Coordinator([vehicle])
        hass = _Hass()
        entity = cover_module.ToyotaWindowsCover(
            coordinator, "Windows", vehicle.vin
        )
        entity.hass = hass

        self.assertTrue(entity.is_closed)
        await entity.async_open_cover()
        self.assertFalse(entity.is_closed)
        self.assertEqual(["open"], vehicle.commands)

        for window in vehicle.features.values():
            window.closed = False
        with patch.object(cover_module.asyncio, "sleep", new=AsyncMock()):
            await hass.coroutines.pop()
        self.assertFalse(entity.is_closed)

        await entity.async_close_cover()
        self.assertTrue(entity.is_closed)
        self.assertEqual(["open", "close"], vehicle.commands)
        for window in vehicle.features.values():
            window.closed = True
        with patch.object(cover_module.asyncio, "sleep", new=AsyncMock()):
            await hass.coroutines.pop()
        self.assertTrue(entity.is_closed)
        self.assertEqual(2, vehicle.polls)
        self.assertEqual(2, coordinator.refreshes)

    async def test_horn_and_buzzer_buttons_send_momentary_commands(self):
        vehicle = _Vehicle()
        coordinator = _Coordinator([vehicle])
        horn = button_module.ToyotaCommandButton(
            "sound_horn", "mdi:bullhorn", coordinator, "Sound Horn", vehicle.vin
        )
        buzzer = button_module.ToyotaCommandButton(
            "buzzer_warning",
            "mdi:bell-alert",
            coordinator,
            "Buzzer Warning",
            vehicle.vin,
        )

        await horn.async_press()
        await buzzer.async_press()

        self.assertEqual(["horn", "buzzer"], vehicle.commands)

    async def test_current_controls_are_not_created_for_legacy_vehicles(self):
        current = _Vehicle(vin="CURRENT")
        legacy = _Vehicle(vin="LEGACY", generation="17CY")
        coordinator = _Coordinator([current, legacy])
        hass = _Hass()
        hass.data = {"toyota_na": {"entry": {"coordinator": coordinator}}}
        config_entry = types.SimpleNamespace(entry_id="entry")
        covers = []
        buttons = []

        await cover_module.async_setup_entry(
            hass,
            config_entry,
            lambda entities, _update_before_add: covers.extend(entities),
        )
        await button_module.async_setup_entry(
            hass,
            config_entry,
            lambda entities, _update_before_add: buttons.extend(entities),
        )

        self.assertEqual(["CURRENT"], [entity.vin for entity in covers])
        self.assertEqual(["CURRENT", "CURRENT"], [entity.vin for entity in buttons])


if __name__ == "__main__":
    unittest.main()
