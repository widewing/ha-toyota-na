"""AWS AppSync WebSocket handler for Toyota vehicle status subscriptions.

The 21MM and 24MM paths use AppSync subscriptions to supplement polled
status with live door, lock, window, cargo opening, and engine updates.

Flow (per APK analysis of SubscribeVehicleStatusDefaultRepo):
1. Connect WebSocket to AppSync realtime endpoint
2. Subscribe to ReceiveVehicleStatus for each VIN
3. On subscription active (start_ack) -> call ConfirmSubscription mutation
4. PreWake + RefreshStatus trigger the vehicle to upload fresh data
5. Data arrives via WebSocket push -> cached and sent to Home Assistant immediately
"""
import asyncio
import base64
import json
import logging
import uuid
from collections.abc import Callable, Mapping
from time import monotonic
from typing import Optional

import aiohttp

from .patch_client import (
    GRAPHQL_WS_ENDPOINT,
    HTTP_TIMEOUT,
    appsync_authorization,
)

_LOGGER = logging.getLogger(__name__)

# Subscription query from Toyota app v3.1.0 APK (yj/h$i.smali)
SUBSCRIBE_VEHICLE_STATUS = (
    "subscription ReceiveVehicleStatus($vin: String!) {"
    " onVehicleStatusUpdated(vin: $vin) {"
    " vin lastUpdateDateTime"
    " vehicleState {"
    " lastUpdateDateTime driverPosition"
    " doors {"
    " driverSide { lock { status } position { status } }"
    " passengerSide { lock { status } position { status } }"
    " rearDriverSide { lock { status } position { status } }"
    " rearPassengerSide { lock { status } position { status } }"
    " }"
    " windows {"
    " driverSide { position { status } }"
    " passengerSide { position { status } }"
    " rearDriverSide { position { status } }"
    " rearPassengerSide { position { status } }"
    " }"
    " hatch { lock { status } position { status } }"
    " hood { position { status } }"
    " moonroof { position { status } }"
    " trunk { lock { status } position { status } }"
    " tailgate { lock { status } position { status } }"
    " engine { running status }"
    " }"
    " location { latitude longitude lastUpdateDateTime }"
    " telemetry {"
    " lastUpdateDateTime"
    " odo { unit value }"
    " fugage { unit value }"
    " range { unit value }"
    " }"
    " }"
    "}"
)


class ToyotaWebSocketHandler:
    """Manages AppSync WebSocket connection for vehicle status push notifications."""

    def __init__(
        self,
        client,
        status_callback: Optional[Callable[[str, dict], None]] = None,
    ):
        """Initialize with a ToyotaOneClient instance (already monkey-patched)."""
        self._client = client
        self._status_callback = status_callback
        self._session = None
        self._ws = None
        self._subscriptions = {}  # vin -> subscription_id
        self._cached_status = {}  # vin -> latest vehicle status dict
        self._confirmed_vins = set()  # VINs that have been confirmed
        self._vins = []
        self._vehicle_contexts: dict[str, dict] = {}
        self._task = None
        self._retry_task = None
        self._running = False
        self._reconnect_delay = 5
        self._max_reconnect_delay = 300
        self._keepalive_timeout = 300
        self._keepalive_deadline = None

    @property
    def is_connected(self):
        return self._ws is not None and not self._ws.closed

    def get_cached_status(self, vin):
        """Get the latest cached vehicle status received via WebSocket."""
        return self._cached_status.get(vin)

    async def start(self, vehicle_contexts):
        """Start the WebSocket handler and subscribe to the given VINs."""
        self._running = True
        if isinstance(vehicle_contexts, Mapping):
            self._vehicle_contexts = {
                vin: dict(context) for vin, context in vehicle_contexts.items()
            }
        else:
            self._vehicle_contexts = {vin: {} for vin in vehicle_contexts}
        self._vins = list(self._vehicle_contexts)
        if self._vins:
            self._task = asyncio.ensure_future(self._run_loop())
            _LOGGER.debug("WebSocket handler started for %d VINs", len(self._vins))

    async def stop(self):
        """Stop the WebSocket handler and clean up resources."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _LOGGER.debug("WebSocket handler stopped")

    async def _run_loop(self):
        """Main loop: connect, listen, reconnect on failure."""
        while self._running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                return
            except Exception as e:
                _LOGGER.debug("WebSocket connection error: %s", e)

            if not self._running:
                return

            _LOGGER.debug(
                "WebSocket: reconnecting in %ds", self._reconnect_delay
            )
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, self._max_reconnect_delay
            )

    async def _connect_and_listen(self):
        """Connect to AppSync WebSocket, subscribe, and process messages."""
        token = await self._client.auth.get_access_token()
        guid = await self._client.auth.get_guid()
        device_id = self._client.auth.get_device_id()

        # AppSync requires auth headers as base64-encoded URL params
        first_vin = self._vins[0] if self._vins else ""
        first_context = self._vehicle_contexts.get(first_vin, {})
        auth_header = appsync_authorization(
            token,
            guid,
            first_vin,
            first_context.get("region", "US"),
            device_id,
        )
        header_b64 = base64.b64encode(
            json.dumps(auth_header).encode()
        ).decode()
        payload_b64 = base64.b64encode(b"{}").decode()
        ws_url = (
            f"{GRAPHQL_WS_ENDPOINT}?header={header_b64}&payload={payload_b64}"
        )

        self._session = aiohttp.ClientSession(timeout=HTTP_TIMEOUT)
        try:
            self._ws = await self._session.ws_connect(
                ws_url, protocols=["graphql-ws"], heartbeat=30
            )
        except Exception:
            await self._session.close()
            self._session = None
            raise

        try:
            # Initiate AppSync connection handshake
            await self._ws.send_json({"type": "connection_init"})
            self._keepalive_deadline = monotonic() + 30

            while self._running:
                msg = await asyncio.wait_for(
                    self._ws.receive(),
                    timeout=max(0, self._keepalive_deadline - monotonic()),
                )
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(
                        json.loads(msg.data), token, guid
                    )
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break
        finally:
            self._subscriptions.clear()
            if self._ws and not self._ws.closed:
                await self._ws.close()
            if self._session and not self._session.closed:
                await self._session.close()
            self._ws = None
            self._session = None
            self._keepalive_deadline = None

    async def _handle_message(self, msg, token, guid):
        """Handle an AppSync WebSocket protocol message."""
        msg_type = msg.get("type")

        if msg_type == "connection_ack":
            self._keepalive_timeout = (
                msg.get("payload", {}).get("connectionTimeoutMs", 300_000) / 1000
            )
            self._keepalive_deadline = monotonic() + self._keepalive_timeout
            _LOGGER.debug(
                "WebSocket: connected, subscribing to %d VINs",
                len(self._vins),
            )
            self._reconnect_delay = 5  # Reset backoff on successful connect
            for vin in self._vins:
                await self._subscribe_vin(vin, token, guid)

        elif msg_type == "start_ack":
            sub_id = msg.get("id")
            vin = next(
                (v for v, sid in self._subscriptions.items() if sid == sub_id),
                None,
            )
            _LOGGER.debug(
                "WebSocket: subscription active for VIN ...%s",
                (vin or "???")[-4:],
            )
            # Per app flow: call ConfirmSubscription after subscription active
            if vin:
                try:
                    context = self._vehicle_contexts.get(vin, {})
                    result = await self._client.graphql_confirm_subscription(
                        vin,
                        context.get("backdoor_type"),
                        context.get("region", "US"),
                    )
                    if result is not None:
                        _LOGGER.debug(
                            "WebSocket: subscription confirmed for VIN ...%s",
                            vin[-4:],
                        )
                    else:
                        _LOGGER.debug(
                            "WebSocket: confirm subscription returned None "
                            "(device limit exceeded?) for VIN ...%s",
                            vin[-4:],
                        )
                except Exception as e:
                    _LOGGER.debug(
                        "WebSocket: confirm subscription failed: %s", e
                    )

        elif msg_type == "data":
            payload = msg.get("payload", {}).get("data", {})
            status = payload.get("onVehicleStatusUpdated")
            if status:
                vin = status.get("vin", "")
                _LOGGER.info(
                    "WebSocket: received vehicle status for VIN ...%s "
                    "(updated: %s)",
                    vin[-4:],
                    status.get("lastUpdateDateTime", "?"),
                )
                self._cached_status[vin] = status
                if self._status_callback is not None:
                    try:
                        self._status_callback(vin, status)
                    except Exception as e:
                        _LOGGER.warning(
                            "WebSocket: failed to apply status for VIN ...%s: %s",
                            vin[-4:],
                            e,
                        )

        elif msg_type == "connection_error" or (msg_type == "error" and not msg.get("id")):
            _LOGGER.warning("WebSocket connection error: %s", msg.get("payload", msg))
            raise ConnectionError("AppSync rejected the connection")

        elif msg_type == "error":
            _LOGGER.debug("WebSocket error: %s", json.dumps(msg)[:500])

        elif msg_type == "ka":
            self._keepalive_deadline = monotonic() + self._keepalive_timeout

    async def _subscribe_vin(self, vin, token, guid):
        """Subscribe to vehicle status updates for a specific VIN."""
        sub_id = str(uuid.uuid4())
        self._subscriptions[vin] = sub_id
        context = self._vehicle_contexts.get(vin, {})
        authorization = appsync_authorization(
            token,
            guid,
            vin,
            context.get("region", "US"),
            self._client.auth.get_device_id(),
        )

        subscription = {
            "id": sub_id,
            "type": "start",
            "payload": {
                "data": json.dumps(
                    {
                        "query": SUBSCRIBE_VEHICLE_STATUS,
                        "variables": {"vin": vin},
                    }
                ),
                "extensions": {
                    "authorization": authorization
                },
            },
        }
        await self._ws.send_json(subscription)
