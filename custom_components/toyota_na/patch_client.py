import asyncio
import json
import logging
import re
import time
from urllib.parse import urljoin, urlencode
import aiohttp

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"
GRAPHQL_ENDPOINT = "https://oa-api.telematicsct.com/graphql"
APPSYNC_API_KEY = "da2-zgeayo2qh5eo7cj6pmdwhwugze"
RESOLVER_API_KEY = "pypIHG015k4ABHWbcI4G0a94F7cC0JDo1OynpAsG"
USER_AGENT = "ToyotaOneApp/3.10.0 (com.toyota.oneapp; build:3100; Android 14) okhttp/4.12.0"

_LOGGER = logging.getLogger(__name__)


# --- GraphQL Operations ---

GRAPHQL_PRE_WAKE = """mutation SendPreWakeCommand($guid: String!) {
  postPreWake(guid: $guid) {
    timestamp
    status { messages { responseCode } }
  }
}"""

GRAPHQL_CONFIRM_SUBSCRIPTION = """mutation ConfirmSubscriptionStatus($vin: String!) {
  confirmSubscriptionActive(vin: $vin, payload: {
    vehicleCapabilities: { backdoorType: "hatch" }
  }) { vin }
}"""

GRAPHQL_REFRESH_STATUS = """mutation RefreshVehicleStatus($vin: String!) {
  postRefreshStatus(vin: $vin) {
    payload { correlationId appRequestNo }
    status { messages { responseCode description } }
    timestamp
  }
}"""


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
        "X-API-KEY": RESOLVER_API_KEY,
        "X-GUID": await self.auth.get_guid(),
        "X-CHANNEL": "ONEAPP",
        "X-BRAND": "T",
        "x-region": "US",
        "X-APPVERSION": "3.4.0",
        "X-LOCALE": "en-US",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

async def get_vehicle_status_17cyplus(self, vin):
    """Vehicle status (doors, locks, windows, hood, hatch) for 21MM/24MM/17CYPLUS."""
    try:
        res = await self.api_get("v1/global/remote/status", {
            "VIN": vin, "vin": vin,
        })
        if res and res.get("vehicleStatus"):
            return res
    except Exception as e:
        _LOGGER.debug("vehicle_status v1/global/remote/status failed: %s", e)
    return None

async def get_engine_status_17cyplus(self, vin):
    """Engine status for 21MM/24MM/17CYPLUS."""
    try:
        res = await self.api_get("v1/global/remote/engine-status", {"VIN": vin, "vin": vin})
        if res:
            return res
    except Exception as e:
        _LOGGER.debug("engine_status v1/global/remote/engine-status failed: %s", e)
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

# --- Remote command results ---
#
# remote/command only reports that Toyota's backend queued the request. The vehicle's actual
# verdict arrives later as a coded message in the account's notification history (the feed
# the official app's inbox shows, e.g. "...: The vehicle is now locked. [DL1]"). When the
# vehicle refuses a command, remote/status and engine-status do not change, so polling them
# cannot distinguish "refused" from "not answered yet"; this feed is the only signal.
#
# Codes observed on a 2023 Highlander Hybrid (17CY+). True = success, False = refused.
REMOTE_COMMAND_RESULT_CODES = {
    "DL1": (True, "Vehicle locked"),
    "DL0": (True, "Vehicle unlocked"),
    "D0": (True, "Doors were already locked"),
    "RES1": (True, "Engine started"),
    "D1": (False, "Refused: vehicle not secured (doors, trunk and hood closed and locked; key fob not inside)"),
    "D3": (False, "Remote start disabled after two unattended 10-minute runs; open, close and lock a door to reset"),
    "D7": (False, "Engine stop refused: engine was not started remotely"),
    "40": (False, "Refused: vehicle in motion or remote climate is on"),
}

_RESULT_CODE_RE = re.compile(r"\[([A-Za-z0-9]+)\]\s*$")


async def get_notification_history(self, vin):
    """Account notification history (the official app's inbox), grouped per VIN."""
    return await self.api_get("v2/notification/history", {"VIN": vin})


def parse_remote_command_results(history, vin=None):
    """Flatten a get_notification_history() payload into coded remote-command results.

    Returns dicts, oldest first: message_id, date (ISO string), code, message, and success
    (True/False for codes in REMOTE_COMMAND_RESULT_CODES, None for codes not seen yet).
    Messages without a trailing [CODE] (e.g. rear-seat reminders) are skipped.
    """
    results = []
    for group in history or []:
        if vin is not None and group.get("vin") != vin:
            continue
        for n in group.get("notifications") or []:
            if n.get("category") != "RemoteCommand":
                continue
            message = n.get("message") or ""
            match = _RESULT_CODE_RE.search(message)
            if not match:
                continue
            code = match.group(1)
            known = REMOTE_COMMAND_RESULT_CODES.get(code)
            results.append({
                "message_id": n.get("messageId"),
                "date": n.get("notificationDate"),
                "code": code,
                "message": message,
                "success": known[0] if known else None,
            })
    results.sort(key=lambda r: r["date"] or "")
    return results


async def wait_for_remote_command_result(self, vin, known_message_ids, timeout=90, interval=4):
    """Poll notification history until a coded result not in known_message_ids appears.

    Snapshot the ids before sending the command:
        before = {r["message_id"] for r in parse_remote_command_results(
            await client.get_notification_history(vin), vin)}
        await client.remote_request_17cyplus(vin, "door-lock")
        result = await client.wait_for_remote_command_result(vin, before)

    Returns the oldest new result dict (see parse_remote_command_results), or None on timeout.
    The vehicle typically answers in 5-15 seconds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await asyncio.sleep(interval)
        try:
            history = await self.get_notification_history(vin)
        except Exception as e:
            _LOGGER.debug("notification history poll failed: %s", e)
            continue
        new = [r for r in parse_remote_command_results(history, vin)
               if r["message_id"] not in known_message_ids]
        if new:
            return new[0]
    return None


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

async def graphql_request(self, operation_name, query, variables):
    """Make a GraphQL request to the AppSync endpoint."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": APPSYNC_API_KEY,
        "x-resolver-api-key": RESOLVER_API_KEY,
        "Authorization": "Bearer " + await self.auth.get_access_token(),
        "vin": variables.get("vin", ""),
        "x-guid": await self.auth.get_guid(),
        "x-deviceid": self.auth.get_device_id(),
        "X-APPBRAND": "T",
        "x-channel": "ONEAPP",
        "X-APPVERSION": "3.4.0",
        "X-OSNAME": "Android",
        "X-OSVERSION": "14",
        "X-LOCALE": "en-US",
        "User-Agent": USER_AGENT,
    }
    payload = json.dumps({
        "operationName": operation_name,
        "query": query,
        "variables": variables,
    })
    async with aiohttp.ClientSession() as session:
        async with session.post(GRAPHQL_ENDPOINT, headers=headers, data=payload) as resp:
            body = await resp.text()
            if resp.status >= 400:
                _LOGGER.debug("GraphQL %s error: HTTP %d: %s", operation_name, resp.status, body[:500])
                return None
            result = json.loads(body)
            if result.get("errors"):
                err = result["errors"][0]
                _LOGGER.debug("GraphQL %s error: %s: %s", operation_name, err.get("errorType"), err.get("message"))
                return None
            return result.get("data")


async def graphql_pre_wake(self, guid):
    """Send pre-wake command to wake the vehicle's telematics unit."""
    return await self.graphql_request("SendPreWakeCommand", GRAPHQL_PRE_WAKE, {"guid": guid})


async def graphql_confirm_subscription(self, vin):
    """Confirm subscription is active for this VIN."""
    return await self.graphql_request("ConfirmSubscriptionStatus", GRAPHQL_CONFIRM_SUBSCRIPTION, {"vin": vin})


async def graphql_refresh_status(self, vin):
    """Request vehicle to upload fresh status via GraphQL."""
    return await self.graphql_request("RefreshVehicleStatus", GRAPHQL_REFRESH_STATUS, {"vin": vin})


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
