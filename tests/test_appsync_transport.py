"""Protocol tests for AppSync status and 24MM remote commands."""

import asyncio
import base64
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import unittest
from unittest.mock import patch

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components/toyota_na/patch_client.py"
SPEC = importlib.util.spec_from_file_location("appsync_patch_client", MODULE_PATH)
patch_client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch_client)


class _Auth:
    async def get_access_token(self):
        return "token"

    async def get_guid(self):
        return "guid"

    def get_device_id(self):
        return "device"


class _Message:
    type = aiohttp.WSMsgType.TEXT

    def __init__(self, body):
        self.data = json.dumps(body)


class _WebSocket:
    def __init__(self):
        self.sent = []
        self.subscription_id = None
        self.stage = 0

    async def send_json(self, value):
        self.sent.append(value)
        if value.get("type") == "start":
            self.subscription_id = value["id"]

    async def receive(self):
        if self.stage == 0:
            body = {"type": "connection_ack"}
        elif self.stage == 1:
            body = {"type": "start_ack", "id": self.subscription_id}
        else:
            request_no = 41 if self.stage == 2 else 42
            body = {
                "type": "data",
                "id": self.subscription_id,
                "payload": {
                    "data": {
                        "onPostRemoteCallback": {
                            "vin": "TESTVIN24",
                            "appRequestNo": request_no,
                            "status": "COMPLETED",
                            "commandEnded": True,
                        }
                    }
                },
            }
        self.stage += 1
        return _Message(body)


class _SocketContext:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _WebSocketSession:
    def __init__(self, websocket):
        self.websocket = websocket
        self.url = None
        self.protocols = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def ws_connect(self, url, protocols, heartbeat):
        self.url = url
        self.protocols = protocols
        return _SocketContext(self.websocket)


class _CommandClient:
    def __init__(self):
        self.auth = _Auth()
        self.command_calls = []

    async def graphql_send_remote_command(self, vin, command, region):
        self.command_calls.append((vin, command, region))
        return {
            "payload": {
                "correlationId": "correlation",
                "requestNo": 42,
            }
        }


class _Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def text(self):
        return json.dumps(
            {"data": {"getVehicleStatus": {"vin": "TESTVIN24"}}}
        )


class _HttpSession:
    def __init__(self):
        self.headers = None
        self.payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def post(self, url, headers, data):
        self.headers = headers
        self.payload = json.loads(data)
        return _Response()


class _HttpClient:
    auth = _Auth()
    graphql_request = patch_client.graphql_request


class RequestTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_stalled_requests_time_out_without_replaying(self):
        calls = []

        async def stall(request):
            calls.append(request.path)
            await asyncio.sleep(0.1)
            return web.json_response({})

        class Client(_HttpClient):
            api_request = patch_client.api_request

            async def _auth_headers(self):
                return {}

        app = web.Application()
        app.router.add_post("/command", stall)
        app.router.add_post("/graphql", stall)
        async with TestServer(app) as server:
            with (
                patch.object(patch_client, "HTTP_TIMEOUT", aiohttp.ClientTimeout(total=0.02)),
                patch.object(patch_client, "GRAPHQL_ENDPOINT", str(server.make_url("/graphql"))),
            ):
                with self.assertRaises(TimeoutError):
                    await Client().api_request("POST", str(server.make_url("/command")), json={})
                with self.assertRaises(TimeoutError):
                    await Client().graphql_request("Status", "query", {"vin": "TESTVIN"})
        self.assertEqual(["/command", "/graphql"], calls)


class AppSyncTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_command_subscribes_before_sending_and_uses_region(self):
        websocket = _WebSocket()
        session = _WebSocketSession(websocket)
        client = _CommandClient()

        with patch.object(
            patch_client.aiohttp,
            "ClientSession",
            return_value=session,
        ):
            result = await patch_client.remote_request_24mm(
                client,
                "TESTVIN24",
                "door-lock",
                "CA",
            )

        self.assertEqual("completed", result["status"].lower())
        self.assertEqual(
            [("TESTVIN24", "door-lock", "CA")],
            client.command_calls,
        )
        self.assertEqual("connection_init", websocket.sent[0]["type"])
        subscription = websocket.sent[1]
        self.assertEqual("start", subscription["type"])
        document = json.loads(subscription["payload"]["data"])
        self.assertIn("onPostRemoteCallback", document["query"])
        authorization = subscription["payload"]["extensions"][
            "authorization"
        ]
        self.assertEqual("CA", authorization["x-region"])
        self.assertEqual("T", authorization["X-BRAND"])
        self.assertEqual("device", authorization["x-deviceid"])
        self.assertEqual(["graphql-ws"], session.protocols)

        query = parse_qs(urlparse(session.url).query)
        connection_headers = json.loads(
            base64.b64decode(query["header"][0])
        )
        self.assertEqual("CA", connection_headers["x-region"])
        self.assertEqual("TESTVIN24", connection_headers["vin"])

    async def test_status_query_sends_vehicle_context_headers(self):
        session = _HttpSession()

        with patch.object(
            patch_client.aiohttp,
            "ClientSession",
            return_value=session,
        ):
            result = await patch_client.graphql_get_vehicle_status(
                _HttpClient(),
                "TESTVIN24",
                "hatch",
                "CA",
            )

        self.assertEqual({"vin": "TESTVIN24"}, result)
        self.assertEqual("CA", session.headers["x-region"])
        self.assertEqual("T", session.headers["X-BRAND"])
        self.assertEqual("T", session.headers["X-APPBRAND"])
        self.assertEqual("hatch", session.headers["backdoorType"])
        self.assertEqual("TESTVIN24", session.headers["vin"])
        self.assertEqual("GetVehicleStatus", session.payload["operationName"])


if __name__ == "__main__":
    unittest.main()
