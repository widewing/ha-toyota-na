from toyota_na.client import ToyotaOneClient
from toyota_na.vehicle.base_vehicle import (
    ApiVehicleGeneration,
    ToyotaVehicle,
)
from toyota_na.vehicle.vehicle_generations.seventeen_cy import SeventeenCYToyotaVehicle
from toyota_na.vehicle.vehicle_generations.seventeen_cy_plus import SeventeenCYPlusToyotaVehicle

async def get_vehicles(client: ToyotaOneClient) -> list[ToyotaVehicle]:
    api_vehicles = await client.get_user_vehicle_list()
    supportedGenerations = dict((item.value, item) for item in ApiVehicleGeneration)
    vehicles = []

    for (i, vehicle) in enumerate(api_vehicles):
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
            )

        elif ApiVehicleGeneration(vehicle["generation"]) == ApiVehicleGeneration.CY17:
            vehicle = SeventeenCYToyotaVehicle(
                client=client,
                has_remote_subscription=vehicle["remoteSubscriptionStatus"] == "ACTIVE",
                has_electric=vehicle["evVehicle"] == True,
                model_name=vehicle["modelName"],
                model_year=vehicle["modelYear"],
                vin=vehicle["vin"],
            )

        await vehicle.update()
        vehicles.append(vehicle)

    return vehicles
