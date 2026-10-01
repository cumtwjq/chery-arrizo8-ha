"""JWT expiry is decoded locally without needing Home Assistant."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "chery_arrizo8" / "credentials.py"
spec = importlib.util.spec_from_file_location("chery_credentials", MODULE)
assert spec is not None and spec.loader is not None
credentials = importlib.util.module_from_spec(spec)
spec.loader.exec_module(credentials)


def capture_with_expiry(expiry: datetime) -> dict:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(expiry.timestamp())}).encode()).decode().rstrip("=")
    return {"headers": {"access_token": f"header.{payload}.signature"}}


class CredentialsTest(unittest.TestCase):
    def test_expiry_warning_boundary(self) -> None:
        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        capture = capture_with_expiry(now + timedelta(days=2))
        self.assertEqual(credentials.token_expiry(capture), now + timedelta(days=2))
        self.assertTrue(credentials.expires_soon(capture, now))
        self.assertFalse(credentials.expires_soon(capture, now - timedelta(seconds=1)))

    def test_invalid_token_has_no_expiry(self) -> None:
        self.assertIsNone(credentials.token_expiry({"headers": {"access_token": "bad"}}))
        self.assertFalse(credentials.expires_soon({"headers": {"access_token": "bad"}}))
