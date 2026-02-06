import logging
from urllib.parse import urljoin, urlencode

import aiohttp

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"

# User-Agent matching the Toyota One App to avoid CDN rejection
USER_AGENT = "OneApp/1.0 (com.toyota.oneapp; Android)"

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
        "User-Agent": USER_AGENT,
    }

async def get_vehicle_status_17cyplus(self, vin):
    return await self.api_get("v1/global/remote/status", {"VIN": vin, "X-BRAND": "T"})

async def get_engine_status_17cyplus(self, vin):
    return await self.api_get("v1/global/remote/engine-status", {"VIN": vin, "X-BRAND": "T"})

async def send_refresh_request_17cyplus(self, vin):
    return await self.api_post(
        "/v1/global/remote/refresh-status",
        {
            "guid": await self.auth.get_guid(),
            "deviceId": self.auth.get_device_id(),
            "vin": vin,
        },
        {"VIN": vin, "X-BRAND": "T"},
    )

async def remote_request_17cyplus(self, vin, command):
    return await self.api_post(
        "/v1/global/remote/command", {"command": command}, {"VIN": vin, "X-BRAND": "T"}
    )

async def get_electric_realtime_status(self, vin, generation="17CYPLUS"):
    realtime_electric_status = await self.api_post(
        "v2/electric/realtime-status",
        {},
        {
            "device-id": self.auth.get_device_id(),
            "vin": vin,
            "X-BRAND": "T",
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
        url, {"VIN": vin, "X-BRAND": "T"}
    )
    if "vehicleInfo" in electric_status:
        return electric_status

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
                logging.error(
                    "Toyota API error: %s %s -> %d %s | Response: %s",
                    method, url, resp.status, resp.reason, body[:500]
                )
            resp.raise_for_status()
            try:
                resp_json = await resp.json()
                return resp_json["payload"]
            except:
                logging.error("Error parsing response: %s", await resp.text())
                raise