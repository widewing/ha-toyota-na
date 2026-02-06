import logging
from urllib.parse import urljoin, urlencode

import aiohttp

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"

_LOGGER = logging.getLogger(__name__)


async def get_telemetry(self, vin, region, generation="17CYPLUS"):
    return await self.api_get(
        "/v2/telemetry", {"VIN": vin, "GENERATION": generation, "X-BRAND": "T", "x-region": region}
    )

async def _auth_headers(self):
    return {
        "AUTHORIZATION": "Bearer " + await self.auth.get_access_token(),
        "X-API-KEY": self.API_KEY,
        "X-GUID": await self.auth.get_guid(),
        "X-CHANNEL": "ONEAPP",
        "X-BRAND": "T",
        "x-region": "US",
        "X-APPVERSION": "3.1.0",
    }


async def get_vehicle_status_17cyplus(self, vin):
    """Vehicle status - gracefully handles 400/403 from remote endpoint."""
    try:
        return await self.api_get("v1/global/remote/status", {"VIN": vin})
    except Exception as e:
        _LOGGER.warning("v1/global/remote/status unavailable (%s), skipping", e)
        return None


async def get_engine_status_17cyplus(self, vin):
    """Engine status - gracefully handles 400/403 from remote endpoint."""
    try:
        return await self.api_get("v1/global/remote/engine-status", {"VIN": vin})
    except Exception as e:
        _LOGGER.warning("v1/global/remote/engine-status unavailable (%s), skipping", e)
        return None


async def send_refresh_request_17cyplus(self, vin):
    """Refresh status - gracefully handles 403 gateway block."""
    try:
        return await self.api_post(
            "/v1/global/remote/refresh-status",
            {
                "guid": await self.auth.get_guid(),
                "deviceId": self.auth.get_device_id(),
                "vin": vin,
            },
            {"VIN": vin},
        )
    except Exception as e:
        _LOGGER.warning("refresh-status failed (%s), skipping refresh", e)
        return None


async def remote_request_17cyplus(self, vin, command):
    """Remote command - logs error but still raises for caller handling."""
    return await self.api_post(
        "/v1/global/remote/command", {"command": command}, {"VIN": vin}
    )


async def get_vehicle_status_17cy(self, vin):
    """Legacy vehicle status - gracefully handles 400/403."""
    try:
        return await self.api_get("v2/legacy/remote/status", {"X-BRAND": "T", "VIN": vin})
    except Exception as e:
        _LOGGER.warning("v2/legacy/remote/status unavailable (%s), skipping", e)
        return None


async def get_engine_status_17cy(self, vin):
    """Legacy engine status - gracefully handles 400/403."""
    try:
        return await self.api_get("/v1/legacy/remote/engine-status", {"X-BRAND": "T", "VIN": vin})
    except Exception as e:
        _LOGGER.warning("v1/legacy/remote/engine-status unavailable (%s), skipping", e)
        return None


async def send_refresh_request_17cy(self, vin):
    """Legacy refresh status - gracefully handles 403 gateway block."""
    try:
        return await self.api_post(
            "/v1/legacy/remote/refresh-status",
            {
                "guid": await self.auth.get_guid(),
                "deviceId": self.auth.get_device_id(),
                "deviceType": "Android",
                "vin": vin,
            },
            {"X-BRAND": "T", "VIN": vin},
        )
    except Exception as e:
        _LOGGER.warning("Legacy refresh-status failed (%s), skipping refresh", e)
        return None


async def get_electric_realtime_status(self, vin, generation="17CYPLUS"):
    try:
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
    except Exception as e:
        _LOGGER.warning("Electric realtime status unavailable: %s", e)
        return None


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
