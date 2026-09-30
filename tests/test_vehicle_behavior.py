# ruff: noqa: I001

import asyncio
from copy import deepcopy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "custom_components"
INTEGRATION = COMPONENTS / "toyota_na"

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(COMPONENTS)]
sys.modules.setdefault("custom_components", custom_components)

integration = types.ModuleType("custom_components.toyota_na")
integration.__path__ = [str(INTEGRATION)]
sys.modules.setdefault("custom_components.toyota_na", integration)

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

from custom_components.toyota_na.patch_seventeen_cy_plus import (
    SeventeenCYPlusToyotaVehicle,
)
from custom_components.toyota_na.patch_seventeen_cy import SeventeenCYToyotaVehicle
from custom_components.toyota_na.patch_client import (
    get_telemetry,
    get_vehicle_status_17cyplus,
    graphql_confirm_subscription,
    remote_request_17cy,
)
from custom_components.toyota_na.vehicle_helpers import (
    has_remote_subscription,
    is_electric_vehicle,
)
from custom_components.toyota_na.wake_policy import (
    CONF_WAKE_INTERVAL,
    LAST_VEHICLE_WAKES,
    automatic_wake_due,
    automatic_wake_interval,
    record_vehicle_wake,
)
from custom_components.toyota_na.websocket_handler import ToyotaWebSocketHandler
from custom_components.toyota_na import websocket_handler as websocket_module

import toyota_na.vehicle.vehicle_generations.seventeen_cy as upstream_17cy
import toyota_na.vehicle.vehicle_generations.seventeen_cy_plus as upstream_17cyplus

upstream_17cy.SeventeenCYToyotaVehicle = SeventeenCYToyotaVehicle
upstream_17cyplus.SeventeenCYPlusToyotaVehicle = SeventeenCYPlusToyotaVehicle

from custom_components.toyota_na.patch_vehicle import get_vehicles


LEXUS_21MM_COUPE = {
    "modelYear": "2024",
    "modelName": "LC 500 2-DOOR COUPE",
    "generation": "21MM",
    "brand": "L",
    "region": "US",
    "remoteSubscriptionStatus": "ACTIVE",
    "subscriptionStatus": "SUBSCRIBED",
    "remoteSubscriptionExists": True,
    "remoteServiceCapabilities": {
        "estartStopCapable": True,
        "dlockUnlockCapable": True,
        "powerWindowCapable": False,
        "trunkCommandCapable": False,
        "hornCommandCapable": False,
        "estartEnabled": True,
        "estopEnabled": True,
        "hazardCapable": True,
        "vehicleFinderCapable": True,
    },
    "extendedCapabilities": {
        "rearDriverDoorOpenStatus": True,
        "rearDriverDoorLockStatus": True,
        "rearPassengerDoorOpenStatus": True,
        "rearPassengerDoorLockStatus": True,
        "remoteEngineStartStop": True,
        "doorLockUnlockCapable": True,
        "vehicleFinder": True,
        "lastParkedCapable": True,
    },
    "backdoorType": "trunk",
    "fuelType": "G",
    "evVehicle": False,
}

TWENTY_FOUR_MM_PHEV = {
    "modelYear": "2026",
    "modelName": "RAV4 PLUG-IN HYBRID",
    "generation": "24MM",
    "brand": "T",
    "region": "CA",
    "remoteSubscriptionStatus": None,
    "subscriptionStatus": "subscribed",
    "remoteSubscriptionExists": True,
    "remoteServiceCapabilities": {
        "estartStopCapable": True,
        "dlockUnlockCapable": True,
    },
    "extendedCapabilities": {
        "remoteEngineStartStop": True,
        "doorLockUnlockCapable": True,
    },
    "backdoorType": "hatch",
    "fuelType": "I",
    "evVehicle": False,
}


def make_vehicle(client=None):
    return SeventeenCYPlusToyotaVehicle(
        client=client or object(),
        has_remote_subscription=has_remote_subscription(LEXUS_21MM_COUPE),
        has_electric=is_electric_vehicle(LEXUS_21MM_COUPE),
        model_name=LEXUS_21MM_COUPE["modelName"],
        model_year=LEXUS_21MM_COUPE["modelYear"],
        vin="TESTVIN",
        region=LEXUS_21MM_COUPE["region"],
        generation=ApiVehicleGeneration(LEXUS_21MM_COUPE["generation"]),
        brand=LEXUS_21MM_COUPE["brand"],
        backdoor_type=LEXUS_21MM_COUPE["backdoorType"],
        remote_capabilities=LEXUS_21MM_COUPE["remoteServiceCapabilities"],
        extended_capabilities=LEXUS_21MM_COUPE["extendedCapabilities"],
    )


def make_24mm_vehicle(client=None):
    return SeventeenCYPlusToyotaVehicle(
        client=client or object(),
        has_remote_subscription=has_remote_subscription(TWENTY_FOUR_MM_PHEV),
        has_electric=is_electric_vehicle(TWENTY_FOUR_MM_PHEV),
        model_name=TWENTY_FOUR_MM_PHEV["modelName"],
        model_year=TWENTY_FOUR_MM_PHEV["modelYear"],
        vin="TESTVIN24",
        region=TWENTY_FOUR_MM_PHEV["region"],
        generation=ApiVehicleGeneration(TWENTY_FOUR_MM_PHEV["generation"]),
        brand=TWENTY_FOUR_MM_PHEV["brand"],
        backdoor_type=TWENTY_FOUR_MM_PHEV["backdoorType"],
        remote_capabilities=TWENTY_FOUR_MM_PHEV[
            "remoteServiceCapabilities"
        ],
        extended_capabilities=TWENTY_FOUR_MM_PHEV[
            "extendedCapabilities"
        ],
    )


def make_17cy_vehicle(client=None):
    return SeventeenCYToyotaVehicle(
        client=client or object(),
        has_remote_subscription=True,
        has_electric=False,
        model_name="CAMRY",
        model_year="2018",
        vin="LEGACYVIN",
        region="US",
    )


class VehicleMetadataTests(unittest.TestCase):
    def test_commands_use_reported_capabilities(self):
        vehicle = make_vehicle()

        self.assertTrue(vehicle.supports_command(RemoteRequestCommand.DoorLock))
        self.assertTrue(vehicle.supports_command(RemoteRequestCommand.EngineStart))
        self.assertTrue(vehicle.supports_command(RemoteRequestCommand.HazardsOn))
        self.assertTrue(
            vehicle.supports_command(RemoteRequestCommand.VehicleFinder)
        )

        vehicle._remote_capabilities = {"hazardCapable": False}
        vehicle._extended_capabilities = {}
        self.assertFalse(vehicle.supports_command(RemoteRequestCommand.HazardsOn))
        self.assertTrue(vehicle.supports_command(RemoteRequestCommand.Refresh))

        vehicle._remote_capabilities = {"hazardCapable": None}
        self.assertTrue(vehicle.supports_command(RemoteRequestCommand.HazardsOn))

    def test_vehicle_finder_requires_explicit_capability_and_transport(self):
        vehicle = make_vehicle()
        vehicle._remote_capabilities = {}
        vehicle._extended_capabilities = {}

        self.assertFalse(
            vehicle.supports_command(RemoteRequestCommand.VehicleFinder)
        )

        legacy = SeventeenCYToyotaVehicle(
            client=object(),
            has_remote_subscription=True,
            has_electric=False,
            model_name="CAMRY",
            model_year="2018",
            vin="TESTVIN",
            region="US",
            remote_capabilities={"vehicleFinderCapable": True},
        )
        self.assertFalse(
            legacy.supports_command(RemoteRequestCommand.VehicleFinder)
        )

    def test_explicit_inactive_subscription_takes_precedence(self):
        metadata = {
            "remoteSubscriptionStatus": "INACTIVE",
            "subscriptionStatus": "SUBSCRIBED",
            "remoteSubscriptionExists": True,
        }

        self.assertFalse(has_remote_subscription(metadata))


class VehicleCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_vehicle_finder_uses_newer_remote_command(self):
        calls = []

        class Client:
            async def remote_request_17cyplus(self, *args):
                calls.append(args)

        vehicle = make_vehicle(Client())

        await vehicle.send_command(RemoteRequestCommand.VehicleFinder)

        self.assertEqual(calls, [("TESTVIN", "find-vehicle", "US")])

    async def test_24mm_command_uses_appsync_transport_and_region(self):
        calls = []

        class Client:
            async def remote_request_24mm(self, *args):
                calls.append(args)

            async def remote_request_17cyplus(self, *args):
                raise AssertionError("24MM must not use the REST command path")

        vehicle = make_24mm_vehicle(Client())

        await vehicle.send_command(RemoteRequestCommand.DoorLock)

        self.assertEqual(calls, [("TESTVIN24", "door-lock", "CA")])


class VehicleRefreshTransportTests(unittest.IsolatedAsyncioTestCase):
    class Auth:
        async def get_guid(self):
            return "guid"

    class Client:
        def __init__(self):
            self.auth = VehicleRefreshTransportTests.Auth()
            self.calls = []

        async def graphql_pre_wake(self, *args):
            self.calls.append(("pre_wake", args))

        async def graphql_confirm_subscription(self, *args):
            self.calls.append(("confirm", args))

        async def graphql_refresh_status(self, *args):
            self.calls.append(("graphql_refresh", args))

        async def send_refresh_request_17cyplus(self, *args):
            self.calls.append(("rest_refresh", args))

    async def test_17cyplus_refresh_uses_only_rest(self):
        client = self.Client()
        vehicle = SeventeenCYPlusToyotaVehicle(
            client=client,
            has_remote_subscription=True,
            has_electric=False,
            model_name="HIGHLANDER",
            model_year="2020",
            vin="RESTVIN",
            region="US",
            generation=ApiVehicleGeneration.CY17PLUS,
        )

        await vehicle.poll_vehicle_refresh()

        self.assertEqual(
            client.calls,
            [("rest_refresh", ("RESTVIN", "US"))],
        )

    async def test_21mm_refresh_keeps_graphql_and_rest(self):
        client = self.Client()
        vehicle = make_vehicle(client)

        await vehicle.poll_vehicle_refresh()

        self.assertEqual(
            client.calls,
            [
                ("pre_wake", ("guid", "US")),
                ("confirm", ("TESTVIN", "trunk", "US")),
                ("graphql_refresh", ("TESTVIN", "US")),
                ("rest_refresh", ("TESTVIN", "US")),
            ],
        )

    async def test_24mm_refresh_uses_only_graphql(self):
        client = self.Client()
        vehicle = make_24mm_vehicle(client)

        await vehicle.poll_vehicle_refresh()

        self.assertEqual(
            client.calls,
            [
                ("pre_wake", ("guid", "CA")),
                ("confirm", ("TESTVIN24", "hatch", "CA")),
                ("graphql_refresh", ("TESTVIN24", "CA")),
            ],
        )

    async def test_refresh_failure_is_not_reported_as_success(self):
        class Client(self.Client):
            async def graphql_refresh_status(self, *args):
                raise RuntimeError("refresh rejected")

        with self.assertRaisesRegex(RuntimeError, "refresh rejected"):
            await make_24mm_vehicle(Client()).poll_vehicle_refresh()

    async def test_legacy_refresh_failure_is_not_reported_as_success(self):
        class Client:
            async def send_refresh_request_17cy(self, *args):
                raise RuntimeError("legacy refresh rejected")

        vehicle = SeventeenCYToyotaVehicle(
            client=Client(),
            has_remote_subscription=True,
            has_electric=False,
            model_name="CAMRY",
            model_year="2018",
            vin="LEGACYVIN",
            region="US",
        )

        with self.assertRaisesRegex(RuntimeError, "legacy refresh rejected"):
            await vehicle.poll_vehicle_refresh()


class WakePolicyTests(unittest.TestCase):
    def test_manual_only_never_automatically_wakes(self):
        self.assertFalse(
            automatic_wake_due(
                {},
                {CONF_WAKE_INTERVAL: 0},
                2 * 3600,
                now=100_000,
            )
        )

    def test_missing_or_expired_timestamp_is_due(self):
        self.assertTrue(automatic_wake_due({}, {}, 2 * 3600, now=100_000))
        self.assertTrue(
            automatic_wake_due(
                {"last_refreshed_at": 92_800}, {}, 2 * 3600, now=100_000
            )
        )

    def test_recent_timestamp_is_not_due(self):
        self.assertFalse(
            automatic_wake_due(
                {"last_refreshed_at": 99_000}, {}, 2 * 3600, now=100_000
            )
        )

    def test_invalid_interval_uses_source_default(self):
        self.assertEqual(
            automatic_wake_interval({CONF_WAKE_INTERVAL: "never"}, 2 * 3600),
            2 * 3600,
        )

    def test_legacy_timestamp_applies_during_per_vehicle_migration(self):
        self.assertFalse(
            automatic_wake_due(
                {"last_refreshed_at": 99_000},
                {},
                2 * 3600,
                vin="LEGACYVIN",
                now=100_000,
            )
        )

    def test_one_vehicle_wake_does_not_delay_another_vehicle(self):
        class Entry:
            data = {}

        class ConfigEntries:
            @staticmethod
            def async_update_entry(entry, *, data):
                entry.data = data

        class Hass:
            config_entries = ConfigEntries()

        entry = Entry()
        record_vehicle_wake(Hass(), entry, "FIRSTVIN", now=100_000)

        self.assertFalse(
            automatic_wake_due(
                entry.data,
                {},
                2 * 3600,
                vin="FIRSTVIN",
                now=100_001,
            )
        )
        self.assertTrue(
            automatic_wake_due(
                entry.data,
                {},
                2 * 3600,
                vin="SECONDVIN",
                now=100_001,
            )
        )
        self.assertEqual(
            entry.data[LAST_VEHICLE_WAKES],
            [{"vin": "FIRSTVIN", "timestamp": 100_000}],
        )

    def test_recording_same_vehicle_replaces_its_timestamp(self):
        class Entry:
            data = {
                LAST_VEHICLE_WAKES: [
                    {"vin": "FIRSTVIN", "timestamp": 90_000},
                    {"vin": "SECONDVIN", "timestamp": 91_000},
                ]
            }

        class ConfigEntries:
            @staticmethod
            def async_update_entry(entry, *, data):
                entry.data = data

        class Hass:
            config_entries = ConfigEntries()

        entry = Entry()
        record_vehicle_wake(Hass(), entry, "FIRSTVIN", now=100_000)

        self.assertEqual(
            entry.data[LAST_VEHICLE_WAKES],
            [
                {"vin": "SECONDVIN", "timestamp": 91_000},
                {"vin": "FIRSTVIN", "timestamp": 100_000},
            ],
        )


class VehicleStateTests(unittest.TestCase):
    def test_telemetry_tires_use_their_measurement_timestamp(self):
        legacy = SeventeenCYToyotaVehicle(
            client=object(),
            has_remote_subscription=True,
            has_electric=False,
            model_name="CAMRY",
            model_year="2018",
            vin="LEGACYVIN",
            region="US",
        )
        for vehicle in (legacy, make_vehicle()):
            with self.subTest(generation=vehicle.generation):
                vehicle._parse_telemetry(
                    {
                        "lastTimestamp": "2026-08-14T12:02:00Z",
                        "flTirePressure": {"value": 35, "unit": "psi"},
                        "spareTirePressure": 35,
                        "tirePressureTimestamp": "2026-08-14T12:01:00Z",
                    }
                )
                tire_timestamp = vehicle.features[VehicleFeatures.LastTirePressureTimeStamp].value
                vehicle._parse_telemetry(
                    {
                        "lastTimestamp": "2026-08-14T12:03:00Z",
                        "flTirePressure": {"value": 20, "unit": "psi"},
                        "spareTirePressure": 20,
                        "tirePressureTimestamp": "2026-08-14T12:00:00Z",
                        "fuelLevel": 50,
                    }
                )
                self.assertEqual(vehicle.features[VehicleFeatures.FrontDriverTire].value, 35)
                self.assertEqual(vehicle.features[VehicleFeatures.SpareTirePressure].value, 35)
                self.assertEqual(vehicle.features[VehicleFeatures.FuelLevel].value, 50)
                self.assertEqual(
                    vehicle.features[VehicleFeatures.LastTirePressureTimeStamp].value,
                    tire_timestamp,
                )

                vehicle._parse_telemetry(
                    {
                        "lastTimestamp": "2026-08-14T12:04:00Z",
                        "flTirePressure": {"value": 36, "unit": "psi"},
                    }
                )
                self.assertEqual(vehicle.features[VehicleFeatures.FrontDriverTire].value, 36)

    def test_older_rest_tires_do_not_override_or_block_newer_appsync_tires(self):
        vehicle = make_24mm_vehicle()
        vehicle.apply_graphql_status(
            {
                "vehicleState": {
                    "tires": {
                        "lastUpdateDateTime": "2026-08-14T12:01:00Z",
                        "frontLeft": {"psi": 35},
                    }
                }
            }
        )
        vehicle._parse_telemetry(
            {
                "lastTimestamp": "2026-08-14T12:03:00Z",
                "tirePressureTimestamp": "2026-08-14T12:00:00Z",
                "flTirePressure": {"value": 20, "unit": "psi"},
            }
        )
        self.assertEqual(vehicle.features[VehicleFeatures.FrontDriverTire].value, 35)

        vehicle.apply_graphql_status(
            {
                "vehicleState": {
                    "tires": {
                        "lastUpdateDateTime": "2026-08-14T12:02:00Z",
                        "frontLeft": {"psi": 36},
                    }
                }
            }
        )
        self.assertEqual(vehicle.features[VehicleFeatures.FrontDriverTire].value, 36)

    def test_changed_vehicle_context_does_not_inherit_observations(self):
        previous = make_vehicle()
        previous._parse_telemetry(
            {"lastTimestamp": "2026-08-14T12:02:00Z", "fuelLevel": 75}
        )
        for attribute, value in (
            ("_vin", "OTHERVIN"),
            ("_region", "CA"),
            ("_generation", ApiVehicleGeneration.MM24),
            ("_has_remote_subscription", False),
            ("_has_electric", True),
        ):
            with self.subTest(attribute=attribute):
                vehicle = make_vehicle()
                setattr(vehicle, attribute, value)
                vehicle.inherit_state(previous)
                self.assertEqual(vehicle.features, {})

                vehicle._parse_telemetry(
                    {"lastTimestamp": "2026-08-14T12:00:00Z", "fuelLevel": 50}
                )
                self.assertEqual(vehicle.features[VehicleFeatures.FuelLevel].value, 50)
                self.assertEqual(previous.features[VehicleFeatures.FuelLevel].value, 75)

    def test_legacy_status_parser_does_not_depend_on_value_order(self):
        vehicle = SeventeenCYToyotaVehicle(
            client=object(),
            has_remote_subscription=True,
            has_electric=False,
            model_name="CAMRY",
            model_year="2018",
            vin="LEGACYVIN",
            region="US",
        )

        vehicle._parse_vehicle_status(
            {
                "occurrenceDate": "2026-08-14T12:00:00Z",
                "vehicleStatus": [
                    {
                        "category": "Driver Side",
                        "sections": [
                            {
                                "section": "Door",
                                "values": [
                                    {"value": "unlocked"},
                                    {"value": "closed"},
                                ],
                            }
                        ],
                    }
                ],
            }
        )

        door = vehicle.features[VehicleFeatures.FrontDriverDoor]
        self.assertTrue(door.closed)
        self.assertFalse(door.locked)

    def test_legacy_unknown_status_does_not_become_open(self):
        vehicle = SeventeenCYToyotaVehicle(
            client=object(),
            has_remote_subscription=True,
            has_electric=False,
            model_name="CAMRY",
            model_year="2018",
            vin="LEGACYVIN",
            region="US",
        )

        vehicle._parse_vehicle_status(
            {
                "vehicleStatus": [
                    {
                        "category": "Driver Side",
                        "sections": [
                            {
                                "section": "Door",
                                "values": [{"value": "unknown"}],
                            }
                        ],
                    }
                ]
            }
        )

        self.assertNotIn(VehicleFeatures.FrontDriverDoor, vehicle.features)

    def test_24mm_status_parses_state_tires_and_electric_data(self):
        status = json.loads(
            (ROOT / "tests/fixtures/vehicle_24mm.json").read_text()
        )
        vehicle = make_24mm_vehicle()

        self.assertTrue(vehicle.apply_graphql_status(status))

        driver = vehicle.features[VehicleFeatures.FrontDriverDoor]
        passenger = vehicle.features[VehicleFeatures.FrontPassengerDoor]
        self.assertTrue(driver.closed)
        self.assertTrue(driver.locked)
        self.assertFalse(passenger.closed)
        self.assertFalse(passenger.locked)
        self.assertEqual(
            (35.1, "psi"),
            (
                vehicle.features[VehicleFeatures.FrontDriverTire].value,
                vehicle.features[VehicleFeatures.FrontDriverTire].unit,
            ),
        )
        self.assertEqual(
            (240, "kPa"),
            (
                vehicle.features[VehicleFeatures.SpareTirePressure].value,
                vehicle.features[VehicleFeatures.SpareTirePressure].unit,
            ),
        )
        self.assertEqual(
            100,
            vehicle.features[VehicleFeatures.ChargeLevel].value,
        )
        self.assertEqual(
            48,
            vehicle.features[VehicleFeatures.ChargeDistance].value,
        )
        self.assertFalse(
            vehicle.features[VehicleFeatures.ChargingStatus].closed
        )
        self.assertFalse(
            vehicle.features[VehicleFeatures.RemoteStartStatus].on
        )

    def test_newer_rest_telemetry_survives_older_graphql_telemetry(self):
        vehicle = make_24mm_vehicle()
        vehicle._parse_telemetry(
            {
                "lastTimestamp": "2026-08-14T12:01:00Z",
                "odometer": {"value": 2000, "unit": "mi"},
            }
        )

        vehicle.apply_graphql_status(
            {
                "telemetry": {
                    "lastUpdateDateTime": "2026-08-14T12:00:00Z",
                    "odo": {"value": 1999, "unit": "mi"},
                }
            }
        )

        self.assertEqual(
            2000,
            vehicle.features[VehicleFeatures.Odometer].value,
        )

    def test_placeholder_rear_doors_do_not_create_entities(self):
        vehicle = make_vehicle()
        vehicle.apply_graphql_status(
            {
                "lastUpdateDateTime": "2026-08-13T12:00:00Z",
                "vehicleState": {
                    "doors": {
                        "rearDriverSide": {
                            "position": {"status": None},
                            "lock": {"status": None},
                        },
                        "rearPassengerSide": {
                            "position": {},
                            "lock": {},
                        },
                    },
                    "hatch": {
                        "position": {"status": None},
                        "lock": {"status": None},
                    },
                    "trunk": {"position": {"status": "close"}},
                    "moonroof": {"position": {"status": "unsupported"}},
                },
            }
        )

        self.assertNotIn(VehicleFeatures.RearDriverDoor, vehicle.features)
        self.assertNotIn(VehicleFeatures.RearPassengerDoor, vehicle.features)
        self.assertNotIn(VehicleFeatures.Moonroof, vehicle.features)
        self.assertTrue(vehicle.features[VehicleFeatures.Trunk].closed)

    def test_empty_preferred_backdoor_does_not_hide_reported_trunk(self):
        vehicle = make_vehicle()
        vehicle.apply_graphql_status(
            {
                "vehicleState": {
                    "trunk": {"position": {"status": "close"}}
                }
            }
        )

        vehicle.apply_graphql_status(
            {
                "vehicleState": {
                    "hatch": {
                        "position": {"status": None},
                        "lock": {"status": None},
                    },
                    "trunk": {"position": {"status": "open"}},
                }
            }
        )

        self.assertFalse(vehicle.features[VehicleFeatures.Trunk].closed)

    def test_lock_only_rest_state_remains_position_unknown(self):
        vehicle = make_vehicle()
        vehicle._parse_vehicle_status(
            {
                "occurrenceDate": "2026-08-13T12:00:00Z",
                "vehicleStatus": [
                    {
                        "category": "Driver Side",
                        "sections": [
                            {"section": "Door", "values": [{"value": "locked"}]}
                        ],
                    }
                ],
            }
        )

        door = vehicle.features[VehicleFeatures.FrontDriverDoor]
        self.assertIsNone(door.closed)
        self.assertTrue(door.locked)

    def test_legacy_lock_flags_override_inactive_and_unflagged_values(self):
        for make in (make_17cy_vehicle, make_vehicle):
            for values, expected in (
                ([{"value": "locked", "status": 0}], True),
                ([{"value": "locked", "status": None}], True),
                ([{"value": "locked", "status": "0"}], True),
                ([{"value": "locked", "status": 0}, {"value": "unlocked", "status": 0}], True),
                ([{"value": "unlocked", "status": 0}, {"value": "locked", "status": 1}], True),
                ([{"value": "locked", "status": 0}, {"value": "unlocked", "status": 1}], False),
                ([{"value": "locked"}, {"value": "unlocked", "status": 1}], False),
                ([{"value": "unlocked", "status": 0}], None),
                ([{"value": "locked", "status": 1}, {"value": "unlocked", "status": 1}], None),
                ([{"value": "unknown", "status": 0}], None),
            ):
                for ordered in (values, list(reversed(values))):
                    with self.subTest(make=make.__name__, values=ordered):
                        vehicle = make()
                        vehicle._parse_vehicle_status({"vehicleStatus": [{
                            "category": "Driver Side",
                            "sections": [{"section": "Door", "values": ordered}],
                        }]})
                        door = vehicle.features.get(VehicleFeatures.FrontDriverDoor)
                        self.assertIs(door.locked if door else None, expected)

    def test_unknown_engine_status_does_not_report_stopped(self):
        for make in (make_17cy_vehicle, make_vehicle):
            with self.subTest(make=make.__name__):
                vehicle = make()
                vehicle._parse_engine_status({"status": "unknown"})
                self.assertNotIn(VehicleFeatures.RemoteStartStatus, vehicle.features)
                vehicle._parse_engine_status({"status": "started"})
                for status in (None, "unknown", "", "unavailable"):
                    with self.subTest(status=status):
                        vehicle._parse_engine_status({"status": status})
                        self.assertTrue(vehicle.features[VehicleFeatures.RemoteStartStatus].on)
                vehicle._parse_engine_status({"status": "0"})
                self.assertFalse(vehicle.features[VehicleFeatures.RemoteStartStatus].on)

    def test_rest_charging_state_distinguishes_waiting_and_completion(self):
        for make in (make_17cy_vehicle, make_vehicle):
            for plug_status, charging in ((40, True), (56, True), (12, False), (36, False), (45, False), (60, False)):
                with self.subTest(make=make.__name__, plug_status=plug_status):
                    vehicle = make()
                    vehicle._parse_electric_status({
                        "vehicleInfo": {"chargeInfo": {"plugStatus": plug_status, "connectorStatus": 5}},
                    })
                    self.assertEqual(vehicle.features[VehicleFeatures.ChargingStatus].closed, not charging)

    def test_unknown_charging_state_does_not_create_or_clear_state(self):
        def rest(vehicle, value):
            vehicle._parse_electric_status({"vehicleInfo": {"chargeInfo": {"plugStatus": value}}})

        def graphql(vehicle, value):
            vehicle._parse_graphql_electric_status({"charging": {"chargingState": value}})

        for make, apply in ((make_17cy_vehicle, rest), (make_vehicle, rest), (make_24mm_vehicle, graphql)):
            with self.subTest(make=make.__name__):
                vehicle = make()
                apply(vehicle, "unknown")
                self.assertNotIn(VehicleFeatures.ChargingStatus, vehicle.features)
                apply(vehicle, "40")
                apply(vehicle, "unknown")
                self.assertFalse(vehicle.features[VehicleFeatures.ChargingStatus].closed)

    def test_older_telemetry_cannot_overwrite_newer_window_state(self):
        vehicle = make_vehicle()
        vehicle.apply_graphql_status(
            {
                "lastUpdateDateTime": "2026-08-13T12:00:00Z",
                "vehicleState": {
                    "windows": {"driverSide": {"position": {"status": "open"}}}
                },
            }
        )
        vehicle._parse_telemetry(
            {"lastTimestamp": "2026-08-13T11:59:00Z", "driverWindow": 2}
        )

        window = vehicle.features[VehicleFeatures.FrontDriverWindow]
        self.assertFalse(window.closed)

    def test_newer_telemetry_can_update_window_state(self):
        vehicle = make_vehicle()
        vehicle.apply_graphql_status(
            {
                "lastUpdateDateTime": "2026-08-13T12:00:00Z",
                "vehicleState": {
                    "windows": {"driverSide": {"position": {"status": "open"}}}
                },
            }
        )
        vehicle._parse_telemetry(
            {"lastTimestamp": "2026-08-13T12:01:00Z", "driverWindow": 2}
        )

        window = vehicle.features[VehicleFeatures.FrontDriverWindow]
        self.assertTrue(window.closed)

    def test_telemetry_location_populates_both_location_entities(self):
        vehicle = make_vehicle()

        vehicle._parse_telemetry(
            {
                "lastTimestamp": "2026-08-13T12:01:00Z",
                "vehicleLocation": {
                    "latitude": 34.05,
                    "longitude": -118.25,
                },
            }
        )

        for feature in (
            VehicleFeatures.RealTimeLocation,
            VehicleFeatures.ParkingLocation,
        ):
            with self.subTest(feature=feature):
                location = vehicle.features[feature]
                self.assertEqual(location.lat, 34.05)
                self.assertEqual(location.value, -118.25)

    def test_legacy_timestamp_merge_rejects_older_values(self):
        vehicle = SeventeenCYToyotaVehicle(
            client=object(),
            has_remote_subscription=True,
            has_electric=False,
            model_name="CAMRY",
            model_year="2018",
            vin="LEGACYVIN",
            region="US",
        )
        vehicle._parse_telemetry(
            {
                "lastTimestamp": "2026-08-14T12:01:00Z",
                "fuelLevel": 50,
                "odometer": {"value": 2000, "unit": "mi"},
                "vehicleLocation": {
                    "latitude": 34.05,
                    "longitude": -118.25,
                },
            }
        )

        vehicle._parse_telemetry(
            {
                "lastTimestamp": "2026-08-14T12:00:00Z",
                "fuelLevel": 40,
                "odometer": {"value": 1999, "unit": "mi"},
                "vehicleLocation": {
                    "latitude": 33.95,
                    "longitude": -118.35,
                },
            }
        )
        vehicle._parse_vehicle_status(
            {
                "occurrenceDate": "2026-08-14T11:59:00Z",
                "latitude": 33.85,
                "longitude": -118.45,
                "vehicleStatus": [],
            }
        )

        self.assertEqual(vehicle.features[VehicleFeatures.FuelLevel].value, 50)
        self.assertEqual(vehicle.features[VehicleFeatures.Odometer].value, 2000)
        for feature in (
            VehicleFeatures.RealTimeLocation,
            VehicleFeatures.ParkingLocation,
        ):
            with self.subTest(feature=feature):
                location = vehicle.features[feature]
                self.assertEqual(location.lat, 34.05)
                self.assertEqual(location.value, -118.25)

    def test_location_only_push_is_applied(self):
        vehicle = make_vehicle()

        applied = vehicle.apply_graphql_status(
            {"location": {"latitude": 0.0, "longitude": 0.0}}
        )

        self.assertTrue(applied)
        location = vehicle.features[VehicleFeatures.ParkingLocation]
        self.assertEqual(location.lat, 0.0)
        self.assertEqual(location.value, 0.0)

    def test_malformed_graphql_sections_do_not_drop_other_readings(self):
        status = {
            "lastUpdateDateTime": "2026-09-15T12:00:00Z",
            "vehicleState": {"doors": {"driverSide": {"position": {"status": "close"}}}},
            "location": {"latitude": 1, "longitude": 2},
            "telemetry": {"odo": {"value": 123}},
            "electric": {"battery": {"stateOfChargeDisplay": {"value": 80}}},
            "tripdetails": {"tripA": {"value": 3}},
        }
        readings = {
            "vehicleState": (VehicleFeatures.FrontDriverDoor, "closed", True),
            "location": (VehicleFeatures.ParkingLocation, "lat", 1),
            "telemetry": (VehicleFeatures.Odometer, "value", 123),
            "electric": (VehicleFeatures.ChargeLevel, "value", 80),
            "tripdetails": (VehicleFeatures.TripDetailsA, "value", 3),
        }
        for section in readings:
            for malformed in (["invalid"], "invalid", 7, True, None, [], {}):
                with self.subTest(section=section, malformed=malformed):
                    vehicle = make_24mm_vehicle()
                    update = {**deepcopy(status), section: malformed}
                    original = deepcopy(update)

                    self.assertTrue(vehicle.apply_graphql_status(update))

                    for key, (feature, attribute, expected) in readings.items():
                        if key == section:
                            self.assertNotIn(feature, vehicle.features)
                        else:
                            self.assertEqual(expected, getattr(vehicle.features[feature], attribute))
                    self.assertEqual(original, update)
                    vehicle._parse_graphql_vehicle_status(vehicle._last_graphql_status)

    def test_unusable_graphql_updates_preserve_cached_state(self):
        vehicle = make_24mm_vehicle()
        vehicle.apply_graphql_status({"telemetry": {"odo": {"value": 123}}})
        cached = vehicle._last_graphql_status
        features = vehicle.features.copy()
        for malformed in (None, [], {}, False, True, 7, "invalid", ["invalid"]):
            for update in (malformed, {"telemetry": malformed}):
                with self.subTest(update=update):
                    self.assertFalse(vehicle.apply_graphql_status(update))
                    self.assertIs(cached, vehicle._last_graphql_status)
                    self.assertEqual(features, vehicle.features)

        self.assertTrue(vehicle.apply_graphql_status({
            "telemetry": ["invalid"], "location": {"latitude": 1, "longitude": 2},
        }))
        self.assertEqual(123, vehicle.features[VehicleFeatures.Odometer].value)
        self.assertEqual(1, vehicle.features[VehicleFeatures.ParkingLocation].lat)


class WebSocketTests(unittest.IsolatedAsyncioTestCase):
    def make_connecting_handler(self, frames):
        websocket = AsyncMock()
        websocket.closed = False
        websocket.receive.side_effect = [
            types.SimpleNamespace(
                type=websocket_module.aiohttp.WSMsgType.TEXT,
                data=json.dumps(frame),
            )
            for frame in frames
        ]
        session = MagicMock()
        session.closed = False
        session.ws_connect = AsyncMock(return_value=websocket)
        session.close = AsyncMock()
        auth = types.SimpleNamespace(
            get_access_token=AsyncMock(return_value="token"),
            get_guid=AsyncMock(return_value="guid"),
            get_device_id=lambda: "device",
        )
        handler = ToyotaWebSocketHandler(types.SimpleNamespace(auth=auth))
        handler._running = True
        return handler, websocket, session

    async def test_appsync_keepalive_deadline_ignores_other_traffic(self):
        handler = ToyotaWebSocketHandler(object())
        with patch.object(websocket_module, "monotonic", return_value=100):
            await handler._handle_message(
                {"type": "connection_ack", "payload": {"connectionTimeoutMs": 120_000}},
                "token", "guid",
            )
        self.assertEqual(handler._keepalive_deadline, 220)

        with patch.object(websocket_module, "monotonic", return_value=150):
            await handler._handle_message({"type": "data", "payload": {}}, "token", "guid")
            self.assertEqual(handler._keepalive_deadline, 220)
            await handler._handle_message({"type": "ka"}, "token", "guid")
        self.assertEqual(handler._keepalive_deadline, 270)

    async def test_missing_appsync_keepalive_closes_socket_and_session(self):
        handler, websocket, session = self.make_connecting_handler([
            {"type": "connection_ack", "payload": {"connectionTimeoutMs": 1000}},
        ])
        frames = iter(websocket.receive.side_effect)

        async def receive():
            try:
                return next(frames)
            except StopIteration:
                await asyncio.Event().wait()

        websocket.receive = receive
        with (
            patch.object(websocket_module.aiohttp, "ClientSession", return_value=session),
            patch.object(websocket_module, "monotonic", side_effect=[0, 0, 0, 2]),
            self.assertRaises(asyncio.TimeoutError),
        ):
            await handler._connect_and_listen()

        websocket.close.assert_awaited_once()
        session.close.assert_awaited_once()
        self.assertFalse(handler.is_connected)

    async def test_connection_scoped_errors_close_and_retire_the_connection(self):
        for error in (
            {"type": "error"},
            {"type": "error", "id": None},
            {"type": "connection_error", "payload": {"message": "rejected"}},
        ):
            with self.subTest(error=error):
                handler, websocket, session = self.make_connecting_handler(
                    [{"type": "connection_ack"}, error]
                )
                with (
                    patch.object(websocket_module.aiohttp, "ClientSession", return_value=session),
                    self.assertLogs(websocket_module.__name__, level="WARNING"),
                    self.assertRaises(ConnectionError),
                ):
                    await handler._connect_and_listen()
                self.assertFalse(handler.is_connected)
                self.assertEqual({}, handler._subscriptions)
                websocket.close.assert_awaited_once()
                session.close.assert_awaited_once()

    async def test_subscription_errors_keep_the_connection(self):
        handler = ToyotaWebSocketHandler(object())
        await handler._handle_message(
            {"type": "error", "id": "subscription", "payload": {"message": "denied"}},
            "token", "guid",
        )

    async def test_push_is_forwarded_immediately(self):
        received = []
        handler = ToyotaWebSocketHandler(
            object(), lambda vin, status: received.append((vin, status))
        )
        status = {"vin": "TESTVIN", "vehicleState": {"doors": {}}}

        await handler._handle_message(
            {"type": "data", "payload": {"data": {"onVehicleStatusUpdated": status}}},
            None,
            None,
        )

        self.assertEqual(received, [("TESTVIN", status)])
        self.assertEqual(handler.get_cached_status("TESTVIN"), status)

    async def test_subscription_confirmation_uses_vehicle_context(self):
        calls = []

        class Client:
            async def graphql_confirm_subscription(self, *args):
                calls.append(args)
                return {"vin": args[0]}

        handler = ToyotaWebSocketHandler(Client())
        handler._subscriptions = {"TESTVIN": "subscription"}
        handler._vehicle_contexts = {
            "TESTVIN": {
                "brand": "L",
                "backdoor_type": "trunk",
                "region": "CA",
            }
        }

        await handler._handle_message(
            {"type": "start_ack", "id": "subscription"}, None, None
        )

        self.assertEqual(calls, [("TESTVIN", "trunk", "CA")])

    async def test_subscription_uses_transport_brand_and_vehicle_region(self):
        sent = []

        class Auth:
            def get_device_id(self):
                return "device"

        class Client:
            auth = Auth()

        class WebSocket:
            async def send_json(self, payload):
                sent.append(payload)

        handler = ToyotaWebSocketHandler(Client())
        handler._ws = WebSocket()
        handler._vehicle_contexts = {"TESTVIN": {"brand": "L", "region": "US"}}

        await handler._subscribe_vin("TESTVIN", "token", "guid")

        authorization = sent[0]["payload"]["extensions"]["authorization"]
        self.assertEqual(authorization["X-BRAND"], "T")
        self.assertEqual(authorization["X-APPBRAND"], "T")
        self.assertEqual(authorization["x-region"], "US")
        self.assertEqual(authorization["x-deviceid"], "device")


class ClientMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_pushes_survive_an_inflight_status_poll(self):
        rest_status = {
            "occurrenceDate": "2026-08-14T12:00:00Z",
            "vehicleStatus": [
                {
                    "category": "Driver Side",
                    "sections": [
                        {
                            "section": "Door",
                            "values": [{"value": "closed"}, {"value": "locked"}],
                        }
                    ],
                }
            ],
        }
        graphql_status = {
            "vehicleState": {
                "lastUpdateDateTime": "2026-08-14T12:00:00Z",
                "doors": {
                    "driverSide": {
                        "position": {"status": "close"},
                        "lock": {"status": "lock"},
                    }
                },
            }
        }

        for metadata, status in (
            (LEXUS_21MM_COUPE, rest_status),
            (TWENTY_FOUR_MM_PHEV, graphql_status),
        ):
            with self.subTest(generation=metadata["generation"]):
                polling = asyncio.Event()
                resume = asyncio.Event()

                class Client:
                    block = False

                    async def get_user_vehicle_list(self):
                        return [dict(metadata, vin="TESTVIN")]

                    async def get_telemetry(self, *args):
                        return {}

                    async def get_engine_status_17cyplus(self, *args):
                        return None

                    async def get_status(self, *args):
                        if self.block:
                            polling.set()
                            await resume.wait()
                        return status

                    get_vehicle_status_17cyplus = get_status
                    graphql_get_vehicle_status = get_status

                client = Client()
                current = (await get_vehicles(client))[0]
                handler = ToyotaWebSocketHandler(
                    client, lambda vin, pushed: current.apply_graphql_status(pushed)
                )
                client._ws_handler = handler
                client.block = True
                task = asyncio.create_task(get_vehicles(client))
                try:
                    await asyncio.wait_for(polling.wait(), timeout=1)
                    for pushed in (
                        {
                            "vin": "TESTVIN",
                            "vehicleState": {
                                "lastUpdateDateTime": "2026-08-14T12:01:00Z",
                                "doors": {
                                    "driverSide": {"lock": {"status": "unlock"}}
                                },
                            },
                        },
                        {
                            "vin": "TESTVIN",
                            "location": {
                                "latitude": 34.05,
                                "longitude": -118.25,
                                "lastUpdateDateTime": "2026-08-14T12:02:00Z",
                            },
                        },
                    ):
                        await handler._handle_message(
                            {
                                "type": "data",
                                "payload": {"data": {"onVehicleStatusUpdated": pushed}},
                            },
                            "token",
                            "guid",
                        )
                finally:
                    resume.set()
                    vehicles = await task

                vehicle = vehicles[0]
                self.assertFalse(vehicle.features[VehicleFeatures.FrontDriverDoor].locked)
                self.assertEqual(vehicle.features[VehicleFeatures.ParkingLocation].lat, 34.05)

    async def test_vehicle_status_uses_toyota_transport_headers(self):
        calls = []

        class Client:
            async def api_get(self, *args):
                calls.append(args)
                return {"vehicleStatus": [{"category": "Driver Side"}]}

        result = await get_vehicle_status_17cyplus(Client(), "TESTVIN", "US")

        self.assertIsNotNone(result)
        self.assertEqual(calls[0][0], "v1/global/remote/status")
        self.assertEqual(calls[0][1]["X-BRAND"], "T")
        self.assertNotIn("X-APPBRAND", calls[0][1])
        self.assertEqual(calls[0][1]["VIN"], "TESTVIN")
        self.assertEqual(calls[0][1]["vin"], "TESTVIN")

    async def test_legacy_discovery_keeps_toyota_defaults(self):
        calls = []
        payload = {
            "modelYear": "2018",
            "modelName": "CAMRY",
            "generation": "17CY",
            "region": "US",
            "remoteSubscriptionStatus": "ACTIVE",
            "evVehicle": False,
            "vin": "TESTVIN",
        }

        class Client:
            async def get_user_vehicle_list(self):
                return [payload]

            async def get_vehicle_status_17cy(self, *args):
                calls.append(("status", args))

            async def get_telemetry(self, *args):
                calls.append(("telemetry", args))

            async def get_engine_status_17cy(self, *args):
                calls.append(("engine", args))

        vehicles = await get_vehicles(Client())

        self.assertEqual(vehicles[0].generation, ApiVehicleGeneration.CY17)
        self.assertEqual(vehicles[0].brand, "T")
        self.assertIn(("status", ("TESTVIN", "US")), calls)
        self.assertIn(("telemetry", ("TESTVIN", "US", "17CY")), calls)

    async def test_rest_wins_without_timestamps_but_push_fills_missing_state(self):
        class WebSocketHandler:
            def get_cached_status(self, vin):
                return {
                    "vin": vin,
                    "vehicleState": {
                        "windows": {
                            "driverSide": {"position": {"status": "close"}},
                            "passengerSide": {"position": {"status": "open"}},
                        }
                    },
                }

        class Client:
            _ws_handler = WebSocketHandler()

            async def get_telemetry(self, *args):
                return {}

            async def get_vehicle_status_17cyplus(self, *args):
                return {
                    "vehicleStatus": [
                        {
                            "category": "Driver Side",
                            "sections": [
                                {"section": "Window", "values": [{"value": "open"}]}
                            ],
                        }
                    ]
                }

            async def get_engine_status_17cyplus(self, *args):
                return None

        vehicle = make_vehicle(Client())

        await vehicle.update()

        self.assertFalse(vehicle.features[VehicleFeatures.FrontDriverWindow].closed)
        self.assertFalse(vehicle.features[VehicleFeatures.FrontPassengerWindow].closed)

    async def test_push_received_during_engine_poll_wins(self):
        async def get_engine_status(*args):
            vehicle.apply_graphql_status({
                "vehicleState": {
                    "engine": {"running": True, "lastUpdateDateTime": "2026-09-14T07:01:00Z"},
                },
            })
            return {"status": "0", "date": "2026-09-14T07:00:00Z", "timer": 20}

        client = types.SimpleNamespace(
            get_telemetry=AsyncMock(return_value={}),
            get_vehicle_status_17cyplus=AsyncMock(return_value={}),
            get_engine_status_17cyplus=get_engine_status,
        )
        vehicle = make_vehicle(client)

        await vehicle.update()

        self.assertTrue(vehicle.features[VehicleFeatures.RemoteStartStatus].on)

    async def test_discovery_preserves_metadata_for_common_vehicle_class(self):
        calls = []
        payload = dict(LEXUS_21MM_COUPE, vin="TESTVIN")

        class Client:
            async def get_user_vehicle_list(self):
                return [payload]

            async def get_telemetry(self, *args):
                calls.append(("telemetry", args))

            async def get_vehicle_status_17cyplus(self, *args):
                calls.append(("status", args))

            async def get_engine_status_17cyplus(self, *args):
                calls.append(("engine", args))

        vehicles = await get_vehicles(Client())

        self.assertEqual(len(vehicles), 1)
        vehicle = vehicles[0]
        self.assertEqual(vehicle.generation, ApiVehicleGeneration.MM21)
        self.assertEqual(vehicle.api_generation, "21MM")
        self.assertEqual(vehicle.endpoint_generation, "17CYPLUS")
        self.assertEqual(vehicle.brand, "L")
        self.assertEqual(vehicle.backdoor_type, "trunk")
        self.assertTrue(vehicle.subscribed)
        self.assertFalse(vehicle.electric)
        self.assertIs(vehicle.capabilities, vehicle.remote_capabilities)
        self.assertIn(("telemetry", ("TESTVIN", "US", "17CYPLUS")), calls)
        self.assertIn(("status", ("TESTVIN", "US")), calls)

    async def test_24mm_update_uses_direct_appsync_status(self):
        calls = []
        fixture = json.loads(
            (ROOT / "tests/fixtures/vehicle_24mm.json").read_text()
        )

        class Client:
            async def get_telemetry(self, *args):
                calls.append(("telemetry", args))
                return {}

            async def graphql_get_vehicle_status(self, *args):
                calls.append(("graphql_status", args))
                return fixture

            async def get_vehicle_status_17cyplus(self, *args):
                raise AssertionError("24MM must not poll REST remote status")

            async def get_engine_status_17cyplus(self, *args):
                raise AssertionError("24MM must not poll REST engine status")

            async def get_electric_status(self, *args, **kwargs):
                raise AssertionError("24MM must not poll legacy EV status")

        vehicle = make_24mm_vehicle(Client())

        await vehicle.update()

        self.assertEqual(
            calls,
            [
                ("telemetry", ("TESTVIN24", "CA", "17CYPLUS")),
                ("graphql_status", ("TESTVIN24", "hatch", "CA")),
            ],
        )
        self.assertTrue(
            vehicle.features[VehicleFeatures.FrontDriverDoor].locked
        )

    async def test_vehicle_state_survives_a_partial_followup_poll(self):
        payload = dict(LEXUS_21MM_COUPE, vin="TESTVIN")
        status_calls = 0

        class Client:
            async def get_user_vehicle_list(self):
                return [payload]

            async def get_telemetry(self, *args):
                return {}

            async def get_vehicle_status_17cyplus(self, *args):
                nonlocal status_calls
                status_calls += 1
                if status_calls == 1:
                    return {
                        "occurrenceDate": "2026-08-14T12:00:00Z",
                        "vehicleStatus": [
                            {
                                "category": "Driver Side",
                                "sections": [
                                    {
                                        "section": "Door",
                                        "values": [
                                            {"value": "closed"},
                                            {"value": "locked"},
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                return None

            async def get_engine_status_17cyplus(self, *args):
                return None

        client = Client()
        first = (await get_vehicles(client))[0]
        second = (await get_vehicles(client))[0]

        self.assertIsNot(first, second)
        self.assertTrue(
            second.features[VehicleFeatures.FrontDriverDoor].closed
        )
        self.assertTrue(
            second.features[VehicleFeatures.FrontDriverDoor].locked
        )

    async def test_state_cache_preserves_source_timestamp_ordering(self):
        payload = dict(TWENTY_FOUR_MM_PHEV, vin="TESTVIN24")
        statuses = iter(
            [
                {
                    "telemetry": {
                        "lastUpdateDateTime": "2026-08-14T12:01:00Z",
                        "odo": {"value": 2000, "unit": "mi"},
                    }
                },
                {
                    "telemetry": {
                        "lastUpdateDateTime": "2026-08-14T12:00:00Z",
                        "odo": {"value": 1999, "unit": "mi"},
                    }
                },
            ]
        )

        class Client:
            async def get_user_vehicle_list(self):
                return [payload]

            async def get_telemetry(self, *args):
                return {}

            async def graphql_get_vehicle_status(self, *args):
                return next(statuses)

        client = Client()
        await get_vehicles(client)
        vehicle = (await get_vehicles(client))[0]

        self.assertEqual(
            2000,
            vehicle.features[VehicleFeatures.Odometer].value,
        )

    async def test_lexus_telemetry_uses_toyota_transport_headers(self):
        calls = []

        class Client:
            async def api_get(self, *args):
                calls.append(args)
                return {}

        await get_telemetry(Client(), "TESTVIN", "US", "17CYPLUS")

        self.assertEqual(calls[0][1]["X-BRAND"], "T")
        self.assertNotIn("X-APPBRAND", calls[0][1])
        self.assertEqual(calls[0][1]["x-region"], "US")

    async def test_legacy_command_uses_toyota_transport_headers(self):
        calls = []

        class Auth:
            async def get_guid(self):
                return "guid"

            def get_device_id(self):
                return "device"

        class Client:
            auth = Auth()

            async def api_post(self, *args):
                calls.append(args)
                return {}

        await remote_request_17cy(Client(), "TESTVIN", "DL", 1, "CA")

        self.assertEqual(calls[0][2]["X-BRAND"], "T")
        self.assertNotIn("X-APPBRAND", calls[0][2])
        self.assertEqual(calls[0][2]["x-region"], "CA")

    async def test_graphql_confirmation_uses_reported_backdoor_type(self):
        calls = []

        class Client:
            async def graphql_request(self, *args, **kwargs):
                calls.append((args, kwargs))
                return {}

        await graphql_confirm_subscription(
            Client(), "TESTVIN", "trunk", "CA"
        )

        args, kwargs = calls[0]
        _, _, variables = args
        self.assertEqual(variables, {"vin": "TESTVIN", "backdoorType": "trunk"})
        self.assertEqual(kwargs["region"], "CA")
        self.assertEqual(kwargs["backdoor_type"], "trunk")

if __name__ == "__main__":
    unittest.main()
