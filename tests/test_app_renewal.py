"""Verify credential rotation and reuse of the owner's signed status request."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "chery_arrizo8"
package = types.ModuleType("public_chery_renewal_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
aiohttp = types.ModuleType("aiohttp")
aiohttp.ClientSession = object
sys.modules.setdefault("aiohttp", aiohttp)


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"{package.__name__}.{name}", ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


load("credentials")
load("const")
api = load("api")
app_auth = load("app_auth")
renewal = load("renewal")


class AppRenewalTest(unittest.TestCase):
    def test_daily_and_near_expiry_refresh(self):
        now = datetime(2026, 10, 22, tzinfo=timezone.utc)
        payload = base64.urlsafe_b64encode(json.dumps({"exp": int((now + timedelta(hours=20)).timestamp())}).encode()).decode().rstrip("=")
        data = {
            "app_refresh_token": "refresh",
            "app_last_refresh": (now - timedelta(hours=2)).isoformat(),
            "capture": {"headers": {"access_token": f"header.{payload}.signature"}},
        }
        self.assertTrue(renewal.renewal_due(data, now))
        data["app_last_refresh"] = (now - timedelta(minutes=30)).isoformat()
        self.assertFalse(renewal.renewal_due(data, now))
        data["app_last_refresh"] = (now - timedelta(days=2)).isoformat()
        self.assertTrue(renewal.renewal_due(data, now))
        data["app_refresh_token"] = ""
        self.assertFalse(renewal.renewal_due(data, now))

    def test_replacing_token_preserves_signature_and_vehicle(self):
        envelope = {"sign": "signed-value", "requestId": "original-id", "appId": "app",
                    "version": "1", "data": json.dumps({"vin": "TESTVIN"})}
        capture = api.parse_capture(json.dumps({
            "url": "https://cloudrivechery.mychery.com/cheryAppData/vehicleRealtimeData/TESTVIN",
            "headers": {"access_token": "old.token.value", "userId": "owner", "other": "discard"},
            "body": json.dumps(envelope),
        }))
        updated = api.with_access_token(capture, "new.token.value")
        self.assertEqual(updated["headers"]["access_token"], "new.token.value")
        self.assertEqual(updated["body"], capture["body"])
        self.assertEqual(updated["url"], capture["url"])
        self.assertEqual(updated["headers"]["userId"], "owner")
        self.assertEqual(capture["headers"]["access_token"], "old.token.value")

    def test_refresh_rotation_and_sdk_exchange(self):
        class Response:
            status = 200

            def __init__(self, payload):
                self.payload = payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def raise_for_status(self):
                return None

            async def json(self, **_kwargs):
                return self.payload

        class Session:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if len(self.calls) == 1:
                    return Response({"status": 200, "data": {
                        "access_token": "app-access", "refresh_token": "rotated-refresh"}})
                return Response({"status": 200, "data": {"sdk_token": "a.b.c"}})

        async def check():
            session = Session()
            result = await app_auth.renew_vehicle_token(session, "original-refresh")
            self.assertEqual(result, ("rotated-refresh", "a.b.c"))
            self.assertEqual(session.calls[0][1]["json"]["grant_type"], "refresh_token")
            self.assertEqual(session.calls[1][1]["params"]["access_token"], "app-access")

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
