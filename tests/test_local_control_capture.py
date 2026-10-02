"""Only a successful owner command can become an importable control request."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "local_tool"))
with patch.dict(os.environ, {"ARRIZO8_CONTROL_KIND": "find_car"}):
    import local_control_capture as addon


def fake_flow(*, result: str = "200", vin: str = "test-car"):
    outer = {"appId": "app", "version": "1", "requestId": "request", "sign": "signed",
             "data": json.dumps({"vin": vin, "userId": "test-user"})}
    return SimpleNamespace(
        request=SimpleNamespace(
            method="POST",
            pretty_url="https://cloudrivechery.mychery.com/cheryAppControl/vehicleRemoteControl/vehicleCommand/findCar",
            raw_content=json.dumps(outer).encode(),
            headers={"access_token": "credential", "userid": "test-user", "content-type": "application/json"},
        ),
        response=SimpleNamespace(
            status_code=200,
            raw_content=json.dumps({"resultCode": result, "data": json.dumps({"seq": "sequence"})}).encode(),
        ),
    )


class LocalControlCaptureTest(unittest.TestCase):
    def test_only_successful_matching_vehicle_is_captured(self):
        status = {"body": json.dumps({"data": json.dumps({"vin": "test-car"})}),
                  "headers": {"access_token": "credential", "userid": "test-user"}}
        with patch.object(addon, "load_capture", return_value=status):
            self.assertIsNotNone(addon._capture(fake_flow()))
            self.assertIsNone(addon._capture(fake_flow(result="400")))
            self.assertIsNone(addon._capture(fake_flow(vin="other-car")))


if __name__ == "__main__":
    unittest.main()
