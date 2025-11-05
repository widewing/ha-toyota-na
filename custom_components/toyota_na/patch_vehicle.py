import logging

from toyota_na.client import ToyotaOneClient
from toyota_na.vehicle.base_vehicle import (
    ApiVehicleGeneration,
    ToyotaVehicle,
)
from toyota_na.vehicle.vehicle_generations.seventeen_cy import SeventeenCYToyotaVehicle
from toyota_na.vehicle.vehicle_generations.seventeen_cy_plus import SeventeenCYPlusToyotaVehicle

_LOGGER = logging.getLogger(__name__)

async def get_vehicles(client: ToyotaOneClient) -> list[ToyotaVehicle]:
    api_vehicles = await client.get_user_vehicle_list()

    # Debug logging to see all vehicle data from API
    _LOGGER.debug("=== FULL VEHICLE LIST API RESPONSE ===")
    _LOGGER.debug(api_vehicles)
    _LOGGER.debug("=== END VEHICLE LIST ===")

    supportedGenerations = dict((item.value, item) for item in ApiVehicleGeneration)
    vehicles = []

    for (i, vehicle_data) in enumerate(api_vehicles):
        # Log each vehicle's key attributes
        _LOGGER.info(f"Vehicle {i}: {vehicle_data.get('modelName')} {vehicle_data.get('modelYear')} - Generation: {vehicle_data.get('generation')}, EV: {vehicle_data.get('evVehicle')}, Remote: {vehicle_data.get('remoteSubscriptionStatus')}")
        if vehicle_data["generation"] not in supportedGenerations:
            continue

        vehicle = None
        if (
            ApiVehicleGeneration(vehicle_data["generation"]) == ApiVehicleGeneration.CY17PLUS
            or ApiVehicleGeneration(vehicle_data["generation"]) == ApiVehicleGeneration.MM21
        ):
            vehicle = SeventeenCYPlusToyotaVehicle(
                client=client,
                has_remote_subscription=vehicle_data["remoteSubscriptionStatus"] == "ACTIVE",
                has_electric=vehicle_data["evVehicle"] == True,
                model_name=vehicle_data["modelName"],
                model_year=vehicle_data["modelYear"],
                vin=vehicle_data["vin"],
                region=vehicle_data["region"],
            )

        elif ApiVehicleGeneration(vehicle_data["generation"]) == ApiVehicleGeneration.CY17:
            vehicle = SeventeenCYToyotaVehicle(
                client=client,
                has_remote_subscription=vehicle_data["remoteSubscriptionStatus"] == "ACTIVE",
                has_electric=vehicle_data["evVehicle"] == True,
                model_name=vehicle_data["modelName"],
                model_year=vehicle_data["modelYear"],
                vin=vehicle_data["vin"],
                region=vehicle_data["region"],
            )

        if vehicle:
            # Store additional metadata as custom attributes
            vehicle.metadata = {
                "color": vehicle_data.get("color"),
                "imei": vehicle_data.get("imei"),
                "manufactured_date": vehicle_data.get("manufacturedDate"),
                "date_of_first_use": vehicle_data.get("dateOfFirstUse"),
                "katashiki_code": vehicle_data.get("katashikiCode"),
            }

            # Store subscription information
            vehicle.subscriptions = vehicle_data.get("subscriptions", [])

            vehicle_update = vehicle.update()
            if vehicle_update:
                await vehicle_update
                vehicles.append(vehicle)

    return vehicles
