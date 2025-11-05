from typing import Any, Union, cast
from datetime import datetime

from toyota_na.vehicle.base_vehicle import ToyotaVehicle, VehicleFeatures
from toyota_na.vehicle.entity_types.ToyotaNumeric import ToyotaNumeric

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .base_entity import ToyotaNABaseEntity
from .const import DOMAIN, SENSORS


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
):
    """Set up the sensor platform."""
    sensors = []

    coordinator: DataUpdateCoordinator[list[ToyotaVehicle]] = hass.data[DOMAIN][
        config_entry.entry_id
    ]["coordinator"]

    for vehicle in coordinator.data:
        for feature_sensor in SENSORS:
            feature = vehicle.features.get(
                cast(VehicleFeatures, feature_sensor["feature"])
            )

            entity_config = feature_sensor
            if entity_config and isinstance(feature, ToyotaNumeric):
                if vehicle.electric is False and cast(bool, entity_config["electric"]):
                    continue
                if vehicle.subscribed is False and cast(bool, entity_config["subscription"]):
                    continue
                sensors.append(
                    ToyotaNumericSensor(
                        cast(VehicleFeatures, feature_sensor["feature"]),
                        cast(str, entity_config["icon"]),
                        cast(str, entity_config["unit"]),
                        cast(SensorStateClass, entity_config["state_class"]),
                        coordinator,
                        entity_config["name"],
                        vehicle.vin,
                    )
                )

        # Add caution count sensor if vehicle has remote subscription
        if vehicle.subscribed:
            sensors.append(
                ToyotaCautionCountSensor(
                    coordinator,
                    "Caution Count",
                    vehicle.vin,
                )
            )

        # Add subscription expiration sensors
        if hasattr(vehicle, 'subscriptions') and vehicle.subscriptions:
            for subscription in vehicle.subscriptions:
                if subscription.get('status') == 'ACTIVE':
                    sensors.append(
                        ToyotaSubscriptionSensor(
                            coordinator,
                            f"{subscription.get('displayProductName', 'Unknown')} Subscription",
                            vehicle.vin,
                            subscription.get('subscriptionID'),
                        )
                    )

    async_add_devices(sensors, True)


class ToyotaNumericSensor(ToyotaNABaseEntity):
    _icon: str
    _vehicle_feature: VehicleFeatures

    def __init__(
        self,
        vehicle_feature: VehicleFeatures,
        icon: str,
        unit_of_measurement: str,
        state_class: Union[SensorStateClass, str],
        *args: Any,
    ):
        super().__init__(*args)
        self._icon = icon
        self._state_class = state_class
        self._unit_of_measurement = unit_of_measurement
        self._vehicle_feature = vehicle_feature

    @property
    def icon(self) -> str:
        return self._icon

    @property
    def state(self):
        feat = cast(ToyotaNumeric, self.feature(self._vehicle_feature))
        if feat:
            return feat.value

    @property
    def state_class(self):
        return self.feature(self._vehicle_feature) is not None

    @property
    def unit_of_measurement(self):

        # We need to poll the unit of measure from the service itself to ensure we're passing
        # the correct unit of measure to the sensor.
        if self._unit_of_measurement == "MI_OR_KM":
            feature = cast(ToyotaNumeric, self.feature(self._vehicle_feature))
            if hasattr(feature,'unit'):
                _unit = feature.unit
                if _unit == "mi":
                    return UnitOfLength.MILES
                elif _unit == "km":
                    return UnitOfLength.KILOMETERS

        return self._unit_of_measurement


class ToyotaCautionCountSensor(ToyotaNABaseEntity):
    """Sensor for vehicle caution/warning count."""

    def __init__(self, coordinator, name: str, vin: str):
        """Initialize the caution count sensor."""
        super().__init__(coordinator, name, vin)
        self._attr_icon = "mdi:alert-circle"
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def state(self):
        """Return the caution count."""
        if self.vehicle and hasattr(self.vehicle, 'caution_count'):
            return self.vehicle.caution_count
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.vehicle is not None
            and hasattr(self.vehicle, 'caution_count')
            and self.vehicle.caution_count is not None
        )


class ToyotaSubscriptionSensor(ToyotaNABaseEntity):
    """Sensor for subscription expiration information."""

    def __init__(self, coordinator, name: str, vin: str, subscription_id: str):
        """Initialize the subscription sensor."""
        super().__init__(coordinator, name, vin)
        self._subscription_id = subscription_id
        self._attr_icon = "mdi:calendar-clock"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def state(self):
        """Return the subscription end date as ISO timestamp."""
        subscription = self._get_subscription()
        if subscription and subscription.get('subscriptionEndDate'):
            try:
                # Parse the date string and return as ISO format for timestamp device class
                end_date = datetime.strptime(subscription['subscriptionEndDate'], "%Y-%m-%d")
                return end_date.isoformat()
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self):
        """Return additional subscription details."""
        subscription = self._get_subscription()
        if subscription:
            attrs = {
                "subscription_type": subscription.get('type'),
                "status": subscription.get('status'),
                "remaining_days": subscription.get('subscriptionRemainingDays'),
                "product_code": subscription.get('productCode'),
                "renewable": subscription.get('renewable'),
                "auto_renew": subscription.get('autoRenew'),
            }
            # Add display term if available
            if subscription.get('displayTerm'):
                attrs["display_term"] = subscription['displayTerm']
            return attrs
        return {}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.vehicle is not None
            and self._get_subscription() is not None
        )

    def _get_subscription(self):
        """Get the subscription data for this sensor."""
        if self.vehicle and hasattr(self.vehicle, 'subscriptions'):
            for sub in self.vehicle.subscriptions:
                if sub.get('subscriptionID') == self._subscription_id:
                    return sub
        return None
