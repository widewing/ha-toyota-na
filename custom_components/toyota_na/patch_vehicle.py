from toyota_na.client import ToyotaOneClient
from toyota_na.vehicle.base_vehicle import (
    ApiVehicleGeneration,
    ToyotaVehicle,
)
from toyota_na.vehicle.vehicle_generations.seventeen_cy import SeventeenCYToyotaVehicle
from toyota_na.vehicle.vehicle_generations.seventeen_cy_plus import SeventeenCYPlusToyotaVehicle

from .vehicle_compat import (
    has_remote_subscription,
    infer_backdoor_type,
    is_electric_vehicle,
)


async def get_vehicles(client: ToyotaOneClient) -> list[ToyotaVehicle]:
    api_vehicles = await client.get_user_vehicle_list()
    supportedGenerations = dict((item.value, item) for item in ApiVehicleGeneration)
    vehicles = []

    for (i, vehicle) in enumerate(api_vehicles):
        if vehicle["generation"] not in supportedGenerations:
            continue
        generation = ApiVehicleGeneration(vehicle["generation"])
        remote_subscription = has_remote_subscription(vehicle)
        electric = is_electric_vehicle(vehicle)

        if generation in (
            ApiVehicleGeneration.CY17PLUS,
            ApiVehicleGeneration.MM21,
            ApiVehicleGeneration.MM24,
        ):
            vehicle = SeventeenCYPlusToyotaVehicle(
                client=client,
                has_remote_subscription=remote_subscription,
                has_electric=electric,
                model_name=vehicle["modelName"],
                model_year=vehicle["modelYear"],
                vin=vehicle["vin"],
                region=vehicle["region"],
                generation=generation,
                backdoor_type=infer_backdoor_type(vehicle),
            )

        elif generation == ApiVehicleGeneration.CY17:
            vehicle = SeventeenCYToyotaVehicle(
                client=client,
                has_remote_subscription=remote_subscription,
                has_electric=electric,
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
