"""Tests for config-entry runtime coordination helpers."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components/toyota_na"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, COMPONENT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entity_discovery = load_module("test_entity_discovery", "entity_discovery.py")


class Entity:
    def __init__(self, unique_id):
        self.unique_id = unique_id


class Coordinator:
    def __init__(self):
        self.listeners = []

    def async_add_listener(self, listener):
        self.listeners.append(listener)

        def remove_listener():
            self.listeners.remove(listener)

        return remove_listener

    def notify(self):
        for listener in list(self.listeners):
            listener()


class ConfigEntry:
    def __init__(self):
        self.unload_callbacks = []

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)


class EntityDiscoveryTests(unittest.TestCase):
    def test_adds_new_entities_once_and_unregisters_listener(self):
        coordinator = Coordinator()
        config_entry = ConfigEntry()
        available_ids = ["first"]
        added = []

        entity_discovery.setup_entity_discovery(
            config_entry,
            coordinator,
            lambda entities, update_before_add: added.extend(entities),
            lambda: [Entity(unique_id) for unique_id in available_ids],
        )

        self.assertEqual([entity.unique_id for entity in added], ["first"])
        available_ids.append("second")
        coordinator.notify()
        coordinator.notify()
        self.assertEqual(
            [entity.unique_id for entity in added],
            ["first", "second"],
        )

        config_entry.unload_callbacks[0]()
        self.assertEqual(coordinator.listeners, [])
if __name__ == "__main__":
    unittest.main()
