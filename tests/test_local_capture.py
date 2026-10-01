"""Only successful read-only calls may replace the locally saved request."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_tool"))
import local_capture  # noqa: E402


def fake_flow(*, host: str = "cloudrivechery.mychery.com", valid_response: bool = True):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": 1800000000}).encode()).decode().rstrip("=")
    token = f"head.{payload}.signature"
    body = {
        "sign": "signature",
        "requestId": "request",
        "appId": "app",
        "version": "1",
        "data": json.dumps({"vin": "example-vehicle"}),
    }
    response_data = {"data": json.dumps({"odometer": "100"})} if valid_response else {"data": ""}
    return SimpleNamespace(
        request=SimpleNamespace(
            pretty_url=f"https://{host}/cheryAppData/vehicleRealtimeData/example",
            method="POST",
            raw_content=json.dumps(body).encode(),
            headers={"access_token": token, "content-type": "application/json"},
        ),
        response=SimpleNamespace(status_code=200, raw_content=json.dumps(response_data).encode()),
    )


class CaptureTest(unittest.TestCase):
    def test_rejects_other_hosts_and_failed_status(self) -> None:
        self.assertIsNone(local_capture._validated_capture(fake_flow(host="example.com")))
        self.assertIsNone(local_capture._validated_capture(fake_flow(valid_response=False)))

    def test_saves_once_and_marker_contains_no_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "ready.json"
            local_capture._captured = False
            with patch.object(local_capture, "READY_MARKER", marker), patch.object(
                local_capture, "load_capture", return_value={"headers": {"access_token": "old"}}
            ), patch.object(local_capture, "save_capture") as save:
                flow = fake_flow()
                local_capture.response(flow)
                local_capture.response(flow)
                self.assertEqual(save.call_count, 1)
                metadata = json.loads(marker.read_text(encoding="utf-8"))
                self.assertTrue(metadata["token_changed"])
                self.assertNotIn("access_token", marker.read_text(encoding="utf-8"))
                self.assertNotIn("example-vehicle", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
