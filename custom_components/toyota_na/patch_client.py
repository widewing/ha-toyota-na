import logging
from urllib.parse import urljoin

import aiohttp

async def get_electric_status(self, vin):
    electric_status = await self.api_get(
        "v2/electric/status", {"VIN": vin}
    )
    if "vehicleInfo" in electric_status:
        return electric_status