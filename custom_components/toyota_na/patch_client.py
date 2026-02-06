import logging
from urllib.parse import urljoin, urlencode
import aiohttp

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"
USER_AGENT = "ToyotaOneApp/3.10.0 (com.toyota.oneapp; build:3100; Android 14) okhttp/4.12.0"

_LOGGER = logging.getLogger(__name__)


async def get_telemetry(self, vin, region="US", generation="17CYPLUS"):
    try:
        return await self.api_get(
            "v2/telemetry", {"VIN": vin, "GENERATION": generation, "X-BRAND": "T", "x-region": region}
        )
    except Exception as e:
        _LOGGER.debug("v2/telemetry failed: %s", e)
        return None

async def _auth_headers(self):
    return {
        "AUTHORIZATION": "Bearer " + await self.auth.get_access_token(),
        "X-API-KEY": self.API_KEY,
        "X-GUID": await self.auth.get_guid(),
        "X-CHANNEL": "ONEAPP",
        "X-BRAND": "T",
        "x-region": "US",
        "X-APPVERSION": "3.1.0",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

async def get_vehicle_status_17cyplus(self, vin):
    """Vehicle status via v2 endpoint (v1 is broken for 21MM/TLS3 vehicles)."""
    try:
        res = await self.api_get("v2/remote/status", {"VIN": vin, "X-BRAND": "T", "x-region": "US", "GENERATION": "17CYPLUS"})
        if res and res.get("vehicleStatus"):
            return res
    except Exception as e:
        _LOGGER.debug("vehicle_status v2/remote/status failed: %s", e)
    return None

async def get_engine_status_17cyplus(self, vin):
    """Engine status via v2 (v1/global/remote/engine-status is broken for 21MM)."""
    try:
        res = await self.api_get("v2/remote/engine-status", {"VIN": vin, "X-BRAND": "T", "x-region": "US"})
        if res:
            return res
    except Exception as e:
        _LOGGER.debug("engine_status v2/remote/engine-status failed: %s", e)
    return None

async def send_refresh_request_17cyplus(self, vin):
    """Refresh status via v1/global/remote/refresh-status."""
    try:
        return await self.api_post(
            "v1/global/remote/refresh-status",
            {
                "guid": await self.auth.get_guid(),
                "deviceId": self.auth.get_device_id(),
                "vin": vin,
            },
            {"VIN": vin, "X-BRAND": "T", "x-region": "US"},
        )
    except Exception as e:
        _LOGGER.debug("refresh-status failed: %s", e)
    return None

async def remote_request_17cyplus(self, vin, command):
    """Remote command (lock, unlock, engine start, etc.) via v1/global/remote."""
    return await self.api_post(
        "v1/global/remote/command", {"command": command},
        {"VIN": vin, "X-BRAND": "T", "x-region": "US"}
    )

async def get_vehicle_status_17cy(self, vin):
    """Legacy vehicle status."""
    try:
        return await self.api_get("v2/legacy/remote/status", {"X-BRAND": "T", "VIN": vin})
    except Exception as e:
        _LOGGER.debug("v2/legacy/remote/status failed: %s", e)
        return None

async def get_engine_status_17cy(self, vin):
    """Legacy engine status."""
    try:
        return await self.api_get("v1/legacy/remote/engine-status", {"X-BRAND": "T", "VIN": vin})
    except Exception as e:
        _LOGGER.debug("v1/legacy/remote/engine-status failed: %s", e)
        return None

async def send_refresh_request_17cy(self, vin):
    """Legacy refresh status."""
    try:
        return await self.api_post(
            "v1/legacy/remote/refresh-status",
            {
                "guid": await self.auth.get_guid(),
                "deviceId": self.auth.get_device_id(),
                "deviceType": "Android",
                "vin": vin,
            },
            {"X-BRAND": "T", "VIN": vin},
        )
    except Exception as e:
        _LOGGER.debug("v1/legacy/remote/refresh-status failed: %s", e)
        return None

async def get_electric_realtime_status(self, vin, generation="17CYPLUS"):
    try:
        realtime_electric_status = await self.api_post(
            "v2/electric/realtime-status",
            {},
            {
                "device-id": self.auth.get_device_id(),
                "vin": vin,
                "X-BRAND": "T",
                "x-region": "US",
            },
        )
        if generation == "17CYPLUS":
            return await self.get_electric_status(vin, realtime_electric_status["appRequestNo"])
        elif realtime_electric_status["returnCode"] == "ONE-RES-10000":
            return await self.get_electric_status(vin)
    except Exception as e:
        _LOGGER.debug("Electric realtime status failed: %s", e)
        return None

async def get_electric_status(self, vin, realtime_status=None):
    try:
        url = "v2/electric/status"
        if realtime_status:
            query_params = {"realtime-status": realtime_status}
            url += "?" + urlencode(query_params)

        electric_status = await self.api_get(
            url, {"VIN": vin, "X-BRAND": "T", "x-region": "US"}
        )
        if "vehicleInfo" in electric_status:
            return electric_status
    except Exception as e:
        _LOGGER.debug("Electric status failed: %s", e)
        return None

async def api_request(self, method, endpoint, header_params=None, **kwargs):
    headers = await self._auth_headers()
    if header_params:
        headers.update(header_params)

    if endpoint.startswith("/"):
        endpoint = endpoint[1:]

    url = urljoin(API_GATEWAY, endpoint)

    async with aiohttp.ClientSession() as session:
        async with session.request(
                method, url, headers=headers, **kwargs
        ) as resp:
            if resp.status >= 400:
                body = await resp.text()
                _LOGGER.debug(
                    "Toyota API error: %s %s -> %d %s | Response: %s",
                    method, url, resp.status, resp.reason, body[:500]
                )
            resp.raise_for_status()
            try:
                resp_json = await resp.json()
                if "payload" in resp_json:
                    return resp_json["payload"]
                return resp_json
            except:
                _LOGGER.error("Error parsing response")
                raise
