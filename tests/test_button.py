# ruff: noqa: I001

import asyncio
from enum import Enum
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "custom_components"
INTEGRATION = COMPONENTS / "toyota_na"

custom_components = sys.modules.setdefault(
    "custom_components", types.ModuleType("custom_components")
)
custom_components.__path__ = [str(COMPONENTS)]
integration = sys.modules.setdefault(
    "custom_components.toyota_na", types.ModuleType("custom_components.toyota_na")
)
integration.__path__ = [str(INTEGRATION)]


def module(name):
    value = sys.modules.setdefault(name, types.ModuleType(name))
    value.__path__ = []
    return value


module("homeassistant")
module("homeassistant.components")
module("homeassistant.helpers")


class BinarySensorDeviceClass(Enum):
    BATTERY_CHARGING = "battery_charging"
    DOOR = "door"
    LOCK = "lock"
    RUNNING = "running"
    WINDOW = "window"


class SensorStateClass(Enum):
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"


class SourceType(Enum):
    GPS = "gps"


class UnitOfPressure:
    PSI = "psi"


class Subscriptable:
    @classmethod
    def __class_getitem__(cls, item):
        return cls


class CoordinatorEntity(Subscriptable):
    def __init__(self, coordinator):
        self.coordinator = coordinator


class DataUpdateCoordinator(Subscriptable):
    def __init__(self, data):
        self.data = data
        self.refreshes = 0
        self.listeners = []

    async def async_request_refresh(self):
        self.refreshes += 1

    def async_add_listener(self, listener):
        self.listeners.append(listener)

        def remove_listener():
            self.listeners.remove(listener)

        return remove_listener

    def notify_listeners(self):
        for listener in list(self.listeners):
            listener()


class ConfigEntry:
    def __init__(self):
        self.entry_id = "entry"
        self.title = "primary@example.com"
        self.data = {}
        self.options = {}
        self.unload_callbacks = []

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)


class LockEntity:
    def async_write_ha_state(self):
        pass


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()


class OptionsFlow:
    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id, data_schema):
        return {"type": "form", "step_id": step_id, "data_schema": data_schema}

    def async_abort(self, *, reason):
        return {"type": "abort", "reason": reason}


binary_sensor = module("homeassistant.components.binary_sensor")
binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
binary_sensor.BinarySensorEntity = type("BinarySensorEntity", (), {})
button_component = module("homeassistant.components.button")
button_component.ButtonEntity = type("ButtonEntity", (), {})
lock_component = module("homeassistant.components.lock")
lock_component.LockEntity = LockEntity
device_tracker_component = module("homeassistant.components.device_tracker")
device_tracker_component.SourceType = SourceType
device_tracker_component.TrackerEntity = type("TrackerEntity", (), {})
sensor = module("homeassistant.components.sensor")
sensor.SensorStateClass = SensorStateClass

config_entries = module("homeassistant.config_entries")
config_entries.ConfigEntry = ConfigEntry
config_entries.ConfigFlow = ConfigFlow
config_entries.OptionsFlow = OptionsFlow
core = module("homeassistant.core")
core.callback = lambda function: function
core.HomeAssistant = type("HomeAssistant", (), {})
core.ServiceCall = type("ServiceCall", (), {})
exceptions = module("homeassistant.exceptions")
exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
ha_const = module("homeassistant.const")
ha_const.PERCENTAGE = "%"
ha_const.UnitOfPressure = UnitOfPressure
ha_const.UnitOfLength = types.SimpleNamespace(MILES="mi", KILOMETERS="km")
module("homeassistant.util")
unit_conversion = module("homeassistant.util.unit_conversion")
unit_conversion.PressureConverter = types.SimpleNamespace(convert=mock.Mock())
entity = module("homeassistant.helpers.entity")
entity.DeviceInfo = dict
device_registry = module("homeassistant.helpers.device_registry")
device_registry.async_get = lambda hass: hass.device_registry
entity_registry = module("homeassistant.helpers.entity_registry")
entity_registry.async_get = lambda hass: hass.entity_registry
entity_platform = module("homeassistant.helpers.entity_platform")
entity_platform.AddEntitiesCallback = object
service = module("homeassistant.helpers.service")
service.verify_domain_control = lambda domain: lambda function: function
update_coordinator = module("homeassistant.helpers.update_coordinator")
update_coordinator.CoordinatorEntity = CoordinatorEntity
update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
update_coordinator.UpdateFailed = type("UpdateFailed", (Exception,), {})

import toyota_na.vehicle.base_vehicle as upstream_base
from custom_components.toyota_na.patch_base_vehicle import (
    ApiVehicleGeneration,
    RemoteRequestCommand,
    ToyotaVehicle,
    VehicleFeatures,
)

upstream_base.ApiVehicleGeneration = ApiVehicleGeneration
upstream_base.RemoteRequestCommand = RemoteRequestCommand
upstream_base.ToyotaVehicle = ToyotaVehicle
upstream_base.VehicleFeatures = VehicleFeatures

from custom_components.toyota_na import button
from custom_components.toyota_na import binary_sensor as binary_sensor_platform
from custom_components.toyota_na import config_flow
from custom_components.toyota_na import device_tracker as device_tracker_platform
from custom_components.toyota_na import lock as lock_platform
from custom_components.toyota_na import sensor as sensor_platform
from custom_components.toyota_na.const import DOMAIN
from custom_components.toyota_na.wake_policy import (
    CONF_WAKE_INTERVAL,
    LAST_VEHICLE_WAKES,
    LAST_WAKE_AT,
)
from toyota_na.vehicle.entity_types.ToyotaLocation import ToyotaLocation
from toyota_na.vehicle.entity_types.ToyotaLockableOpening import ToyotaLockableOpening
from toyota_na.vehicle.entity_types.ToyotaOpening import ToyotaOpening
from toyota_na.vehicle.entity_types.ToyotaNumeric import ToyotaNumeric


runtime_spec = importlib.util.spec_from_file_location(
    "custom_components.toyota_na.integration_runtime",
    INTEGRATION / "__init__.py",
)
integration_runtime = importlib.util.module_from_spec(runtime_spec)
sys.modules[runtime_spec.name] = integration_runtime
runtime_spec.loader.exec_module(integration_runtime)


class FakeVehicle:
    def __init__(self, supported, vin="TESTVIN"):
        self.vin = vin
        self.subscribed = True
        self.supported = set(supported)
        self.sent = []
        self.refresh_requests = 0
        self.features = {}
        self.electric = False
        self.backdoor_type = "trunk"
        self.model_year = "2024"
        self.model_name = "LC 500 2-DOOR COUPE"
        self.brand = "L"

    def supports_command(self, command):
        return command in self.supported

    async def send_command(self, command):
        self.sent.append(command)

    async def poll_vehicle_refresh(self):
        self.refresh_requests += 1


class FakeHass:
    def __init__(self, coordinator):
        self.data = {DOMAIN: {"entry": {"coordinator": coordinator}}}
        self.tasks = []
        self.config_entries = self
        self.entity_registry = FakeEntityRegistry()

    def async_create_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task

    def async_update_entry(self, entry, *, data):
        entry.data = data


class FakeEntityRegistry:
    def __init__(self):
        self.entities = {}
        self.removed = []

    def async_get_entity_id(self, platform, domain, unique_id):
        return self.entities.get((platform, domain, unique_id))

    def async_remove(self, entity_id):
        self.removed.append(entity_id)


class ButtonTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        button.COMMAND_REFRESH_DELAY = 0
        lock_platform.COMMAND_REFRESH_DELAY = 0
        self.vehicle = FakeVehicle(
            {
                RemoteRequestCommand.DoorLock,
                RemoteRequestCommand.DoorUnlock,
                RemoteRequestCommand.EngineStart,
                RemoteRequestCommand.EngineStop,
                RemoteRequestCommand.HazardsOn,
                RemoteRequestCommand.VehicleFinder,
            }
        )
        self.coordinator = DataUpdateCoordinator([self.vehicle])
        self.hass = FakeHass(self.coordinator)
        self.config_entry = ConfigEntry()
        self.entities = []

        await button.async_setup_entry(
            self.hass,
            self.config_entry,
            lambda entities, update_before_add: self.entities.extend(entities),
        )
        for entity_instance in self.entities:
            entity_instance.hass = self.hass

    async def test_creates_only_supported_lc_controls(self):
        self.assertEqual(
            [entity.sensor_name for entity in self.entities],
            [
                "Remote Start",
                "Remote Stop",
                "Flash Hazards",
                "Find Vehicle",
                "Refresh Status",
            ],
        )
        self.assertEqual(
            [entity.name for entity in self.entities],
            [
                "Remote Start",
                "Remote Stop",
                "Flash Hazards",
                "Find Vehicle",
                "Refresh Status",
            ],
        )
        self.assertTrue(
            all(entity._attr_has_entity_name for entity in self.entities)
        )

    async def test_command_button_does_not_issue_an_extra_vehicle_wake(self):
        await self.entities[0].async_press()
        await asyncio.gather(*self.hass.tasks)

        self.assertEqual(self.vehicle.sent, [RemoteRequestCommand.EngineStart])
        self.assertEqual(self.vehicle.refresh_requests, 0)
        self.assertEqual(self.coordinator.refreshes, 1)
        self.assertIn(LAST_WAKE_AT, self.config_entry.data)
        self.assertEqual(
            self.config_entry.data[LAST_VEHICLE_WAKES],
            [{"vin": "TESTVIN", "timestamp": self.config_entry.data[LAST_WAKE_AT]}],
        )

    async def test_refresh_button_explicitly_requests_vehicle_status(self):
        await self.entities[-1].async_press()
        await asyncio.gather(*self.hass.tasks)

        self.assertEqual(self.vehicle.refresh_requests, 1)
        self.assertEqual(self.coordinator.refreshes, 1)
        self.assertIn(LAST_WAKE_AT, self.config_entry.data)
        self.assertEqual(
            self.config_entry.data[LAST_VEHICLE_WAKES][0]["vin"],
            "TESTVIN",
        )

    async def test_capability_change_marks_command_unavailable(self):
        self.vehicle.supported.remove(RemoteRequestCommand.HazardsOn)

        self.assertFalse(self.entities[2].available)

    async def test_new_command_capability_adds_button_without_reload(self):
        vehicle = FakeVehicle({RemoteRequestCommand.EngineStart})
        coordinator = DataUpdateCoordinator([vehicle])
        hass = FakeHass(coordinator)
        config_entry = ConfigEntry()
        entities = []

        await button.async_setup_entry(
            hass,
            config_entry,
            lambda added, update_before_add: entities.extend(added),
        )
        self.assertEqual(
            [entity.sensor_name for entity in entities],
            ["Remote Start", "Refresh Status"],
        )

        vehicle.supported.add(RemoteRequestCommand.EngineStop)
        coordinator.notify_listeners()
        coordinator.notify_listeners()

        self.assertEqual(
            [entity.sensor_name for entity in entities],
            ["Remote Start", "Refresh Status", "Remote Stop"],
        )

    async def test_lock_command_does_not_issue_an_extra_vehicle_wake(self):
        entities = []
        await lock_platform.async_setup_entry(
            self.hass,
            self.config_entry,
            lambda added, update_before_add: entities.extend(added),
        )
        lock = entities[0]
        lock.hass = self.hass

        await lock.async_lock()
        await asyncio.gather(*self.hass.tasks)

        self.assertEqual(self.vehicle.sent, [RemoteRequestCommand.DoorLock])
        self.assertEqual(self.vehicle.refresh_requests, 0)
        self.assertEqual(self.coordinator.refreshes, 1)
        self.assertIn(LAST_WAKE_AT, self.config_entry.data)

    async def test_failed_lock_command_clears_transition_state(self):
        async def fail_command(command):
            raise RuntimeError("command rejected")

        self.vehicle.send_command = fail_command
        entities = []
        await lock_platform.async_setup_entry(
            self.hass,
            self.config_entry,
            lambda added, update_before_add: entities.extend(added),
        )
        lock = entities[0]
        lock.hass = self.hass

        with self.assertRaisesRegex(RuntimeError, "command rejected"):
            await lock.async_lock()

        self.assertFalse(lock._state_changing)
        self.assertNotIn(LAST_WAKE_AT, self.config_entry.data)
        self.assertEqual(self.hass.tasks, [])

    async def test_lock_availability_tracks_capabilities(self):
        entities = []
        await lock_platform.async_setup_entry(
            self.hass,
            self.config_entry,
            lambda added, update_before_add: entities.extend(added),
        )

        lock = entities[0]
        self.assertTrue(lock._attr_has_entity_name)
        self.assertIsNone(lock.name)
        self.assertEqual(lock.unique_id, "TESTVIN.")

        self.vehicle.supported.remove(RemoteRequestCommand.DoorUnlock)

        self.assertFalse(lock.available)


class BinarySensorCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_position_only_door_does_not_report_lock_state(self):
        for closed in (True, False):
            with self.subTest(closed=closed):
                vehicle = FakeVehicle(set())
                vehicle.features[VehicleFeatures.FrontDriverDoor] = ToyotaOpening(closed)
                coordinator = DataUpdateCoordinator([vehicle])
                entities = []
                await binary_sensor_platform.async_setup_entry(
                    FakeHass(coordinator),
                    ConfigEntry(),
                    lambda added, update: entities.extend(added),
                )
                lock = next(
                    entity for entity in entities
                    if entity.device_class == BinarySensorDeviceClass.LOCK
                )
                door = next(
                    entity for entity in entities
                    if entity.device_class == BinarySensorDeviceClass.DOOR
                )
                self.assertIsNone(lock.is_on)
                self.assertFalse(lock.available)
                self.assertEqual(door.is_on, not closed)
                self.assertTrue(door.available)

                vehicle.features[VehicleFeatures.FrontDriverDoor] = ToyotaLockableOpening(
                    closed=None, locked=True
                )
                self.assertFalse(lock.is_on)
                self.assertTrue(lock.available)
                self.assertIsNone(door.is_on)
                self.assertFalse(door.available)

    async def test_tailgate_removes_stale_trunk_entities(self):
        vehicle = FakeVehicle(set())
        vehicle.backdoor_type = "tailgate"
        coordinator = DataUpdateCoordinator([vehicle])
        hass = FakeHass(coordinator)
        config_entry = ConfigEntry()
        hass.entity_registry.entities = {
            (
                "binary_sensor",
                DOMAIN,
                "TESTVIN.Trunk",
            ): "binary_sensor.testvin_trunk",
            (
                "binary_sensor",
                DOMAIN,
                "TESTVIN.Trunk Door Lock",
            ): "binary_sensor.testvin_trunk_door_lock",
        }

        await binary_sensor_platform.async_setup_entry(
            hass,
            config_entry,
            lambda entities, update_before_add: None,
        )

        self.assertEqual(
            hass.entity_registry.removed,
            [
                "binary_sensor.testvin_trunk",
                "binary_sensor.testvin_trunk_door_lock",
            ],
        )


class NumericSensorTests(unittest.IsolatedAsyncioTestCase):
    async def test_pressure_sensor_converts_reported_units_to_psi(self):
        for value, unit, expected in (
            (240, "kPa", 34.809058),
            (2.4, "bar", 34.809058),
            (0, "kPa", 0),
        ):
            with self.subTest(value=value, unit=unit):
                vehicle = FakeVehicle(set())
                vehicle.features[VehicleFeatures.SpareTirePressure] = ToyotaNumeric(value, unit)
                coordinator = DataUpdateCoordinator([vehicle])
                entities = []
                await sensor_platform.async_setup_entry(
                    FakeHass(coordinator),
                    ConfigEntry(),
                    lambda added, update: entities.extend(added),
                )
                pressure = entities[0]
                with mock.patch.object(
                    unit_conversion.PressureConverter, "convert", return_value=expected
                ) as convert:
                    self.assertEqual(pressure.state, expected)
                    self.assertEqual(pressure.unit_of_measurement, "psi")
                    convert.assert_called_once_with(value, unit, "psi")

    async def test_native_and_missing_pressure_values_do_not_need_conversion(self):
        vehicle = FakeVehicle(set())
        coordinator = DataUpdateCoordinator([vehicle])
        pressure = sensor_platform.ToyotaNumericSensor(
            VehicleFeatures.SpareTirePressure,
            "mdi:car-tire-alert",
            "psi",
            SensorStateClass.MEASUREMENT,
            coordinator,
            "Spare Tire Pressure",
            vehicle.vin,
        )
        for value, unit in ((35, "psi"), (35, ""), (35, None), (None, "kPa")):
            with self.subTest(value=value, unit=unit):
                vehicle.features[VehicleFeatures.SpareTirePressure] = ToyotaNumeric(value, unit)
                with mock.patch.object(unit_conversion.PressureConverter, "convert") as convert:
                    self.assertEqual(pressure.state, value)
                    convert.assert_not_called()


class DeviceTrackerTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsubscribed_vehicle_exposes_both_location_entities(self):
        vehicle = FakeVehicle(set())
        vehicle.subscribed = False
        location = ToyotaLocation(34.05, -118.25)
        vehicle.features = {
            VehicleFeatures.ParkingLocation: location,
            VehicleFeatures.RealTimeLocation: location,
        }
        coordinator = DataUpdateCoordinator([vehicle])
        hass = FakeHass(coordinator)
        entities = []

        await device_tracker_platform.async_setup_entry(
            hass,
            ConfigEntry(),
            lambda added, update_before_add: entities.extend(added),
        )

        self.assertEqual(
            [entity.sensor_name for entity in entities],
            ["Last Parked Location", "Current Location"],
        )


class CoordinatorUpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_wakes_schedule_one_followup_poll(self):
        vehicles = [
            FakeVehicle(set(), vin="FIRSTVIN"),
            FakeVehicle(set(), vin="SECONDVIN"),
        ]
        coordinator = DataUpdateCoordinator(vehicles)
        hass = FakeHass(coordinator)
        entry = ConfigEntry()

        with (
            mock.patch.object(
                integration_runtime,
                "get_vehicles",
                mock.AsyncMock(return_value=vehicles),
            ),
            mock.patch.object(
                integration_runtime,
                "automatic_wake_due",
                return_value=True,
            ),
            mock.patch.object(
                integration_runtime,
                "COMMAND_REFRESH_DELAY",
                0,
            ),
        ):
            result = await integration_runtime.update_vehicles_status(
                hass,
                object(),
                entry,
                coordinator,
            )
            await asyncio.gather(*hass.tasks)

        self.assertEqual(result, vehicles)
        self.assertEqual(
            [vehicle.refresh_requests for vehicle in vehicles],
            [1, 1],
        )
        self.assertEqual(len(hass.tasks), 1)
        self.assertEqual(coordinator.refreshes, 1)


class OptionsFlowTests(unittest.IsolatedAsyncioTestCase):
    def make_flow(self, *, options=None):
        config_entry = ConfigEntry()
        config_entry.options = options or {}
        return config_flow.ToyotaNAOptionsFlow(config_entry)

    async def test_default_preserves_existing_two_hour_behavior(self):
        result = await self.make_flow().async_step_init()

        self.assertEqual(
            result["data_schema"]({}),
            {CONF_WAKE_INTERVAL: str(2 * 3600)},
        )

    async def test_manual_only_is_saved(self):
        result = await self.make_flow().async_step_init(
            {CONF_WAKE_INTERVAL: "0"}
        )

        self.assertEqual(
            result,
            {
                "type": "create_entry",
                "title": "",
                "data": {CONF_WAKE_INTERVAL: 0},
            },
        )

    async def test_saved_interval_is_selected_when_reopened(self):
        for interval in (0, 12 * 3600):
            with self.subTest(interval=interval):
                result = await self.make_flow(
                    options={CONF_WAKE_INTERVAL: interval}
                ).async_step_init()

                self.assertEqual(
                    result["data_schema"]({}),
                    {CONF_WAKE_INTERVAL: str(interval)},
                )


if __name__ == "__main__":
    unittest.main()
