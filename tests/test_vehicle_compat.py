"""Tests for current Toyota vehicle-list and status compatibility values."""

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components/toyota_na/vehicle_compat.py"
SPEC = importlib.util.spec_from_file_location("vehicle_compat", MODULE_PATH)
vehicle_compat = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vehicle_compat)


class VehicleCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_path = ROOT / "tests/fixtures/vehicle_24mm.json"
        cls.vehicle = json.loads(fixture_path.read_text())

    def test_current_subscription_shapes_enable_connected_entities(self):
        self.assertTrue(vehicle_compat.has_remote_subscription(self.vehicle))
        self.assertTrue(
            vehicle_compat.has_remote_subscription({"remoteSubscriptionExists": True})
        )
        self.assertTrue(
            vehicle_compat.has_remote_subscription(
                {"extendedCapabilities": {"doorLockUnlockCapable": True}}
            )
        )
        self.assertFalse(vehicle_compat.has_remote_subscription({}))

    def test_phev_fuel_type_enables_electric_entities(self):
        self.assertTrue(vehicle_compat.is_electric_vehicle(self.vehicle))
        self.assertTrue(vehicle_compat.is_electric_vehicle({"fuelType": "E"}))
        self.assertFalse(vehicle_compat.is_electric_vehicle({"fuelType": "G"}))

    def test_24mm_opening_aliases_are_normalized(self):
        driver = self.vehicle["vehicleState"]["doors"]["driverSide"]
        passenger = self.vehicle["vehicleState"]["doors"]["passengerSide"]

        self.assertTrue(vehicle_compat.closed_from_status(driver["position"]["status"]))
        self.assertTrue(vehicle_compat.locked_from_status(driver["lock"]["status"]))
        self.assertFalse(
            vehicle_compat.closed_from_status(passenger["position"]["status"])
        )
        self.assertFalse(vehicle_compat.locked_from_status(passenger["lock"]["status"]))
        self.assertIsNone(vehicle_compat.closed_from_status("unknown"))
        self.assertIsNone(vehicle_compat.locked_from_status("unknown"))

    def test_backdoor_type_uses_payload_then_model_fallback(self):
        self.assertEqual(
            "liftgate",
            vehicle_compat.infer_backdoor_type({"backdoorType": "liftgate"}),
        )
        self.assertEqual(
            "hatch",
            vehicle_compat.infer_backdoor_type({"modelName": "RAV4 XSE"}),
        )
        self.assertEqual(
            "trunk",
            vehicle_compat.infer_backdoor_type({"modelName": "Camry"}),
        )


if __name__ == "__main__":
    unittest.main()
