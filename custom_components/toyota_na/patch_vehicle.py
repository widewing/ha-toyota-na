from typing import Union

from toyota_na.client import ToyotaOneClient
from toyota_na.vehicle.base_vehicle import (
    ApiVehicleGeneration,
    ToyotaVehicle,
)
from toyota_na.vehicle.vehicle_generations.seventeen_cy import SeventeenCYToyotaVehicle
from toyota_na.vehicle.vehicle_generations.seventeen_cy_plus import SeventeenCYPlusToyotaVehicle

async def get_vehicles(
    client: ToyotaOneClient, exclude_vins: Union[set, None] = None
) -> list[ToyotaVehicle]:
    """:param exclude_vins: VINs to skip entirely (no vehicle object constructed, no API calls
    made for them) -- vehicles a user has explicitly excluded via the Configure option."""
    exclude_vins = exclude_vins or set()
    api_vehicles = await client.get_user_vehicle_list()
    supportedGenerations = dict((item.value, item) for item in ApiVehicleGeneration)
    vehicles = []

    for (i, vehicle) in enumerate(api_vehicles):
        if vehicle["generation"] not in supportedGenerations:
            continue
        if vehicle["vin"] in exclude_vins:
            continue
        api_generation = vehicle["generation"]
        if (
            ApiVehicleGeneration(api_generation) == ApiVehicleGeneration.CY17PLUS
            or ApiVehicleGeneration(api_generation) == ApiVehicleGeneration.MM21
            or ApiVehicleGeneration(api_generation) == ApiVehicleGeneration.MM24
        ):
            vehicle = SeventeenCYPlusToyotaVehicle(
                client=client,
                has_remote_subscription=vehicle["remoteSubscriptionStatus"] == "ACTIVE",
                has_electric=vehicle["evVehicle"] == True,
                model_name=vehicle["modelName"],
                model_year=vehicle["modelYear"],
                vin=vehicle["vin"],
                region=vehicle["region"],
                backdoor_type=vehicle.get("backdoorType"),
                capabilities=vehicle.get("remoteServiceCapabilities"),
                api_generation=api_generation,
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
