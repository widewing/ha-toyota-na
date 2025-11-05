import logging
from urllib.parse import urljoin, urlencode

import aiohttp

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"

_LOGGER = logging.getLogger(__name__)

async def get_telemetry(self, vin, region, generation="17CYPLUS"):
    return await self.api_get(
        "/v2/telemetry", {"VIN": vin, "GENERATION": generation, "X-BRAND": "T", "x-region": region}
    )

async def get_vehicle_health(self, vin):
    """Attempt to get vehicle health report which may include tire pressure."""
    try:
        _LOGGER.info(f"Attempting to fetch vehicle health report for VIN {vin}")
        response = await self.api_get("/v2/vehicle/health", {"VIN": vin})
        _LOGGER.debug(f"Vehicle health response: {response}")
        return response
    except Exception as e:
        _LOGGER.debug(f"Vehicle health endpoint not available: {e}")
        return None

async def get_vehicle_status_details(self, vin):
    """Attempt to get detailed vehicle status which may include tire pressure."""
    try:
        _LOGGER.info(f"Attempting to fetch detailed vehicle status for VIN {vin}")
        response = await self.api_get("/v2/vehicle/status/details", {"VIN": vin})
        _LOGGER.debug(f"Vehicle status details response: {response}")
        return response
    except Exception as e:
        _LOGGER.debug(f"Vehicle status details endpoint not available: {e}")
        return None

async def _auth_headers(self):
    return {
        "AUTHORIZATION": "Bearer " + await self.auth.get_access_token(),
        "X-API-KEY": self.API_KEY,
        "X-GUID": await self.auth.get_guid(),
        "X-CHANNEL": "ONEAPP"
    }

async def get_electric_realtime_status(self, vin, generation="17CYPLUS"):
    realtime_electric_status = await self.api_post(
        "v2/electric/realtime-status",
        {},
        {
            "device-id": self.auth.get_device_id(),
            "vin": vin,
        },
    )
    if generation == "17CYPLUS":
        return await self.get_electric_status(vin, realtime_electric_status["appRequestNo"])
    elif realtime_electric_status["returnCode"] == "ONE-RES-10000":
        return await self.get_electric_status(vin)


async def get_electric_status(self, vin, realtime_status=None):
    url = "v2/electric/status"
    if realtime_status:
        query_params = {"realtime-status": realtime_status}
        url += "?" + urlencode(query_params)

    electric_status = await self.api_get(
        url, {"VIN": vin}
    )
    if "vehicleInfo" in electric_status:
        return electric_status

async def api_request(self, method, endpoint, header_params=None, **kwargs):
    headers = await self._auth_headers()
    if header_params:
        headers.update(header_params)

    if endpoint.startswith("/"):
        endpoint = endpoint[1:]

    async with aiohttp.ClientSession() as session:
        async with session.request(
                method, urljoin(API_GATEWAY, endpoint), headers=headers, **kwargs
        ) as resp:
            resp.raise_for_status()
            try:
                resp_json = await resp.json()
                return resp_json["payload"]
            except:
                logging.error("Error parsing response: %s", await resp.text())
                raise