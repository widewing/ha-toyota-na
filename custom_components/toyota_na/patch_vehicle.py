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

    for (i, vehicle) in enumerate(api_vehicles):
        # Log each vehicle's key attributes
        _LOGGER.info(f"Vehicle {i}: {vehicle.get('modelName')} {vehicle.get('modelYear')} - Generation: {vehicle.get('generation')}, EV: {vehicle.get('evVehicle')}, Remote: {vehicle.get('remoteSubscriptionStatus')}")
        if vehicle["generation"] not in supportedGenerations:
            continue
        if (
            ApiVehicleGeneration(vehicle["generation"]) == ApiVehicleGeneration.CY17PLUS
            or ApiVehicleGeneration(vehicle["generation"]) == ApiVehicleGeneration.MM21
        ):
            vehicle = SeventeenCYPlusToyotaVehicle(
                client=client,
                has_remote_subscription=vehicle["remoteSubscriptionStatus"] == "ACTIVE",
                has_electric=vehicle["evVehicle"] == True,
                model_name=vehicle["modelName"],
                model_year=vehicle["modelYear"],
                vin=vehicle["vin"],
                region=vehicle["region"],
            )

        elif ApiVehicleGeneration(vehicle["generation"]) == ApiVehicleGeneration.CY17:
            vehicle = SeventeenCYToyotaVehicle(
                client=client,
                has_remote_subscription=vehicle["remoteSubscriptionStatus"] == "ACTIVE",
                has_electric=vehicle["evVehicle"] == True,
                model_name=vehicle["modelName"],
                model_year=vehicle["modelYear"],
                vin=vehicle["vin"],
                region=vehicle["region"],
            )

        vehicle_update = vehicle.update()
        if vehicle_update:
            await vehicle_update
            vehicles.append(vehicle)

    return vehicles
