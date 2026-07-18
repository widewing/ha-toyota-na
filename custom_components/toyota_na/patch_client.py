import asyncio
import base64
import json
import logging
import uuid
from urllib.parse import urljoin, urlencode

import aiohttp

API_GATEWAY = "https://onecdn.telematicsct.com/oneapi/"
GRAPHQL_ENDPOINT = "https://oa-api.telematicsct.com/graphql"
GRAPHQL_WS_ENDPOINT = "wss://oa-api.telematicsct.com/graphql/realtime"
GRAPHQL_HOST = "oa-api.telematicsct.com"
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

GRAPHQL_CONFIRM_SUBSCRIPTION = """mutation ConfirmSubscriptionStatus($vin: String!, $backdoorType: String!) {
  confirmSubscriptionActive(vin: $vin, payload: {
    vehicleCapabilities: { backdoorType: $backdoorType }
  }) { vin }
}"""

GRAPHQL_REFRESH_STATUS = """mutation RefreshVehicleStatus($vin: String!) {
  postRefreshStatus(vin: $vin) {
    payload { correlationId appRequestNo }
    status { messages { responseCode description } }
    timestamp
  }
}"""

GRAPHQL_GET_VEHICLE_STATUS = """query GetVehicleStatus($vin: String!) {
  getVehicleStatus(vin: $vin) {
    vin lastUpdateDateTime
    vehicleState {
      lastUpdateDateTime driverPosition
      doors {
        driverSide { lock { status } position { status } }
        passengerSide { lock { status } position { status } }
        rearDriverSide { lock { status } position { status } }
        rearPassengerSide { lock { status } position { status } }
      }
      windows {
        driverSide { position { status } }
        passengerSide { position { status } }
        rearDriverSide { position { status } }
        rearPassengerSide { position { status } }
      }
      hatch { lock { status } position { status } }
      hood { position { status } }
      moonroof { position { status } }
      trunk { lock { status } position { status } }
      tailgate { lock { status } position { status } }
      tires {
        frontLeft { psi kpa bar displayLowTirePressureWarning }
        frontRight { psi kpa bar displayLowTirePressureWarning }
        rearLeft { psi kpa bar displayLowTirePressureWarning }
        rearRight { psi kpa bar displayLowTirePressureWarning }
        spare { psi kpa bar displayLowTirePressureWarning }
        lastUpdateDateTime
      }
      engine { running lastUpdateDateTime status }
    }
    tripdetails {
      lastUpdateDateTime
      tripA { value unit }
      tripB { value unit }
      tripCount { value unit }
    }
    location { latitude longitude lastUpdateDateTime }
    telemetry {
      lastUpdateDateTime
      odo { unit value }
      fugage { unit value }
      range { unit value }
      totalAverageFuelConsumption { unit value }
      averageFuelConsumptionSinceStart { unit value }
    }
    electric {
      lastUpdateDateTime
      battery {
        chargeRemainingAmount { unit value }
        powerSupplyPossibleTime { unit value }
        travelableDistance { unit value }
        travelableDistanceAC { unit value }
        plugInEnergy { unit value }
        stateOfChargeDisplay { unit value }
      }
      charging {
        chargeType chargingStatus chargingState
        remainingChargeTime { unit value }
        remainingChargeTimeTo80Percent { unit value }
        connector { status plugInInfo plugStatus }
        chargeSettings {
          targetLimit { value unit }
          maxACCurrent { value setting }
          maxDCPower { value setting }
          lastUpdateDateTime
        }
        lastUpdateDateTime
      }
      gasoline {
        powerSupplyPossibleTime { unit value }
        travelableDistance { unit value }
      }
    }
  }
}"""

GRAPHQL_REMOTE_COMMAND_STATUS = """subscription ReceiveRemoteCommandStatus($vin: String!) {
  onPostRemoteCallback(vin: $vin) {
    appRequestNo type category remoteCommandType message status vin command commandEnded
  }
}"""

GRAPHQL_SEND_REMOTE_COMMAND = """mutation SendRemoteCommand($command: String!, $autoFixCommands: [String]!) {
  executeRemoteCommand(commandInputBody: {
    command: $command
    autofixCommands: $autoFixCommands
  }) {
    payload { requestNo correlationId returnCode }
    status { messages { responseCode description detailedDescription } }
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
        "X-API-KEY": self.API_KEY,
        "X-GUID": await self.auth.get_guid(),
        "X-CHANNEL": "ONEAPP",
        "X-BRAND": "T",
        "x-region": "US",
        "X-APPVERSION": "3.1.0",
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

async def graphql_request(
    self,
    operation_name,
    query,
    variables,
    vin=None,
    headers=None,
    raise_errors=False,
):
    """Make a GraphQL request to the AppSync endpoint."""
    request_headers = {
        "Content-Type": "application/json",
        "x-api-key": APPSYNC_API_KEY,
        "x-resolver-api-key": RESOLVER_API_KEY,
        "Authorization": "Bearer " + await self.auth.get_access_token(),
        "vin": vin or variables.get("vin", ""),
        "x-guid": await self.auth.get_guid(),
        "x-deviceid": self.auth.get_device_id(),
        "X-APPBRAND": "T",
        "x-channel": "ONEAPP",
        "X-APPVERSION": "3.1.0",
        "X-OSNAME": "Android",
        "X-OSVERSION": "14",
        "X-LOCALE": "en-US",
        "User-Agent": USER_AGENT,
    }
    if headers:
        request_headers.update(headers)
    payload = json.dumps({
        "operationName": operation_name,
        "query": query,
        "variables": variables,
    })
    async with aiohttp.ClientSession() as session:
        async with session.post(
            GRAPHQL_ENDPOINT, headers=request_headers, data=payload
        ) as resp:
            body = await resp.text()
            if resp.status >= 400:
                _LOGGER.debug("GraphQL %s error: HTTP %d: %s", operation_name, resp.status, body[:500])
                if raise_errors:
                    raise RuntimeError(
                        "Toyota GraphQL %s failed with HTTP %d"
                        % (operation_name, resp.status)
                    )
                return None
            result = json.loads(body)
            if result.get("errors"):
                err = result["errors"][0]
                _LOGGER.debug("GraphQL %s error: %s: %s", operation_name, err.get("errorType"), err.get("message"))
                if raise_errors:
                    extensions = err.get("extensions") or {}
                    code = (
                        extensions.get("responseCode")
                        or extensions.get("code")
                        or err.get("errorType")
                    )
                    detail = (
                        extensions.get("detailedDescription")
                        or err.get("message")
                        or "Toyota rejected the AppSync request"
                    )
                    if code:
                        detail = "%s [%s]" % (detail, code)
                    raise RuntimeError(detail)
                return None
            return result.get("data")


async def graphql_pre_wake(self, guid):
    """Send pre-wake command to wake the vehicle's telematics unit."""
    return await self.graphql_request("SendPreWakeCommand", GRAPHQL_PRE_WAKE, {"guid": guid})


async def graphql_confirm_subscription(
    self, vin, backdoor_type="hatch", region="US"
):
    """Confirm subscription is active for this VIN."""
    return await self.graphql_request(
        "ConfirmSubscriptionStatus",
        GRAPHQL_CONFIRM_SUBSCRIPTION,
        {"vin": vin, "backdoorType": backdoor_type},
        headers={
            "x-brand": "T",
            "x-region": region,
            "backdoorType": backdoor_type,
        },
    )


async def graphql_refresh_status(self, vin):
    """Request vehicle to upload fresh status via GraphQL."""
    return await self.graphql_request("RefreshVehicleStatus", GRAPHQL_REFRESH_STATUS, {"vin": vin})


async def graphql_get_vehicle_status(
    self, vin, backdoor_type="hatch", region="US"
):
    """Read the current 24MM state; subscriptions only deliver later updates."""
    data = await self.graphql_request(
        "GetVehicleStatus",
        GRAPHQL_GET_VEHICLE_STATUS,
        {"vin": vin},
        headers={
            "x-brand": "T",
            "x-region": region,
            "backdoorType": backdoor_type,
        },
    )
    return data.get("getVehicleStatus") if data else None


async def graphql_send_remote_command(self, vin, command):
    """Submit a 24MM remote command after its callback subscription is ready."""
    data = await self.graphql_request(
        "SendRemoteCommand",
        GRAPHQL_SEND_REMOTE_COMMAND,
        {"command": command, "autoFixCommands": []},
        vin=vin,
        raise_errors=True,
    )
    execution = data.get("executeRemoteCommand") if data else None
    correlation_id = (
        ((execution or {}).get("payload") or {}).get("correlationId")
    )
    if correlation_id:
        return execution

    messages = ((execution or {}).get("status") or {}).get("messages") or []
    message = messages[0] if messages else {}
    detail = (
        message.get("detailedDescription")
        or message.get("description")
        or "Toyota did not return a correlation ID for the remote command."
    )
    code = message.get("responseCode")
    if code:
        detail = "%s [%s]" % (detail, code)
    raise RuntimeError(detail)


def _remote_socket_error(message):
    payload = message.get("payload") or {}
    errors = payload.get("errors") if isinstance(payload, dict) else None
    error = errors[0] if errors else payload
    if isinstance(error, dict):
        return (
            error.get("message")
            or error.get("error")
            or "Toyota rejected the AppSync remote-command subscription."
        )
    return "Toyota rejected the AppSync remote-command subscription."


async def _receive_remote_socket_message(ws, timeout):
    message = await asyncio.wait_for(ws.receive(), timeout=timeout)
    if message.type == aiohttp.WSMsgType.TEXT:
        return json.loads(message.data)
    if message.type in (
        aiohttp.WSMsgType.CLOSE,
        aiohttp.WSMsgType.CLOSED,
        aiohttp.WSMsgType.ERROR,
    ):
        raise RuntimeError("Toyota closed the AppSync remote-command connection.")
    return {}


async def _wait_for_remote_socket_event(ws, expected_type, subscription_id=None):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 15
    while loop.time() < deadline:
        message = await _receive_remote_socket_message(
            ws, max(1, deadline - loop.time())
        )
        message_type = message.get("type")
        if message_type == "ka":
            continue
        if message_type in ("connection_error", "error"):
            raise RuntimeError(_remote_socket_error(message))
        if message_type == expected_type and (
            subscription_id is None or message.get("id") == subscription_id
        ):
            return
    raise RuntimeError("Toyota's AppSync remote-command connection timed out.")


async def _wait_for_remote_command_result(ws, vin, subscription_id):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 60
    while loop.time() < deadline:
        message = await _receive_remote_socket_message(
            ws, max(1, deadline - loop.time())
        )
        message_type = message.get("type")
        if message_type == "ka":
            continue
        if message_type in ("connection_error", "error"):
            raise RuntimeError(_remote_socket_error(message))
        if message_type != "data" or message.get("id") != subscription_id:
            continue

        callback = (
            ((message.get("payload") or {}).get("data") or {}).get(
                "onPostRemoteCallback"
            )
            or {}
        )
        if callback.get("vin") != vin:
            continue
        status = str(callback.get("status", "")).lower()
        detail = callback.get("message")
        if status == "completed":
            return callback
        if status == "in_progress":
            continue
        if status in ("error", "timeout") or callback.get("commandEnded") is True:
            raise RuntimeError(
                detail or "Toyota ended the remote command with status %s." % status
            )
    raise RuntimeError(
        "Toyota accepted the command but did not report completion within 60 seconds."
    )


async def remote_request_24mm(self, vin, command):
    """Run a 24MM command through AppSync and wait for Toyota's callback."""
    token = await self.auth.get_access_token()
    guid = await self.auth.get_guid()
    authorization = {
        "host": GRAPHQL_HOST,
        "x-api-key": APPSYNC_API_KEY,
        "Authorization": "Bearer " + token,
        "x-channel": "ONEAPP",
        "vin": vin,
        "x-guid": guid,
    }
    query = urlencode(
        {
            "header": base64.b64encode(
                json.dumps(authorization).encode()
            ).decode(),
            "payload": base64.b64encode(b"{}").decode(),
        }
    )
    websocket_url = "%s?%s" % (GRAPHQL_WS_ENDPOINT, query)

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            websocket_url, protocols=["graphql-ws"], heartbeat=30
        ) as ws:
            await ws.send_json({"type": "connection_init"})
            await _wait_for_remote_socket_event(ws, "connection_ack")

            subscription_id = str(uuid.uuid4())
            await ws.send_json(
                {
                    "id": subscription_id,
                    "type": "start",
                    "payload": {
                        "data": json.dumps(
                            {
                                "query": GRAPHQL_REMOTE_COMMAND_STATUS,
                                "variables": {"vin": vin},
                            }
                        ),
                        "extensions": {"authorization": authorization},
                    },
                }
            )
            await _wait_for_remote_socket_event(
                ws, "start_ack", subscription_id
            )
            await self.graphql_send_remote_command(vin, command)
            return await _wait_for_remote_command_result(
                ws, vin, subscription_id
            )


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
