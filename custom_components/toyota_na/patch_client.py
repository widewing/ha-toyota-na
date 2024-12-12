import logging
from urllib.parse import urljoin

import aiohttp

API_GATEWAY = "https://oneapi-east.telematicsct.com/"

async def get_electric_status(self, vin):
    electric_status = await self.api_get(
        "v2/electric/status", {"VIN": vin}
    )
    if "vehicleInfo" in electric_status:
        return electric_status

async def api_request(self, method, endpoint, header_params=None, **kwargs):
    headers = await self._auth_headers()
    if header_params:
        headers.update(header_params)

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