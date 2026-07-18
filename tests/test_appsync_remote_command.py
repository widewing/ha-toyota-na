"""Protocol tests for the 24MM AppSync remote-command flow."""

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "custom_components/toyota_na/patch_client.py"


class _WSMsgType:
    TEXT = "text"
    CLOSE = "close"
    CLOSED = "closed"
    ERROR = "error"


fake_aiohttp = types.ModuleType("aiohttp")
fake_aiohttp.WSMsgType = _WSMsgType
original_aiohttp = sys.modules.get("aiohttp")
if original_aiohttp is None:
    sys.modules["aiohttp"] = fake_aiohttp
SPEC = importlib.util.spec_from_file_location("patch_client", MODULE_PATH)
patch_client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch_client)
if original_aiohttp is None:
    sys.modules.pop("aiohttp", None)


class _Message:
    type = _WSMsgType.TEXT

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
            body = {
                "type": "data",
                "id": self.subscription_id,
                "payload": {
                    "data": {
                        "onPostRemoteCallback": {
                            "vin": "TESTVIN",
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


class _Session:
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


class _Auth:
    async def get_access_token(self):
        return "token"

    async def get_guid(self):
        return "guid"


class _Client:
    def __init__(self):
        self.auth = _Auth()
        self.command_calls = []

    async def graphql_send_remote_command(self, vin, command):
        self.command_calls.append((vin, command))
        return {"payload": {"correlationId": "correlation"}}


class AppSyncRemoteCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_subscribes_before_sending_and_waits_for_completion(self):
        websocket = _WebSocket()
        session = _Session(websocket)
        client = _Client()

        with patch.object(
            patch_client.aiohttp,
            "ClientSession",
            return_value=session,
            create=True,
        ):
            result = await patch_client.remote_request_24mm(
                client, "TESTVIN", "door-lock"
            )

        self.assertEqual("completed", result["status"].lower())
        self.assertEqual([("TESTVIN", "door-lock")], client.command_calls)
        self.assertEqual("connection_init", websocket.sent[0]["type"])
        subscription = websocket.sent[1]
        self.assertEqual("start", subscription["type"])
        document = json.loads(subscription["payload"]["data"])
        self.assertIn("onPostRemoteCallback", document["query"])
        self.assertEqual("TESTVIN", document["variables"]["vin"])
        self.assertEqual(["graphql-ws"], session.protocols)


if __name__ == "__main__":
    unittest.main()
