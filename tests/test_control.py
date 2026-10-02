"""A command must match the verified vehicle, action and token."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "chery_arrizo8"
package = types.ModuleType("chery_control_test")
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
api = load("api")
control = load("control")


def capture(path: str, token: str = "credential", state: str | None = None) -> dict:
    inner = {"vin": "test-car", "userId": "test-user"}
    if state is not None:
        inner["doorState"] = state
    return {
        "url": "https://cloudrivechery.mychery.com" + path,
        "headers": {"access_token": token, "userid": "test-user", "content-type": "application/json"},
        "body": json.dumps({"appId": "app", "version": "1", "requestId": "unique", "sign": "signed", "data": json.dumps(inner)}),
    }


STATUS = capture("/cheryAppData/vehicleRealtimeData/getVehicleConditionData")


class ControlTest(unittest.TestCase):
    def test_combined_import_needs_one_paste(self):
        base = "/cheryAppControl/vehicleRemoteControl/vehicleCommand/"
        bundle = {
            "status": STATUS,
            "controls": {
                "find_car": capture(base + "findCar"),
                "unlock": capture(base + "doorState", state="1"),
                "lock": capture(base + "doorState", state="0"),
            },
        }
        parsed_status, controls = control.parse_request_import(json.dumps(bundle))
        self.assertEqual(parsed_status["url"], STATUS["url"])
        self.assertEqual(set(controls), {"find_car", "unlock", "lock"})
        with self.assertRaises(api.CaptureError):
            control.parse_request_import(json.dumps({"status": STATUS, "controls": {"find_car": bundle["controls"]["lock"]}}))

    def test_known_actions_and_wrong_target_rejected(self):
        base = "/cheryAppControl/vehicleRemoteControl/vehicleCommand/"
        for action, state, expected in (("findCar", None, "find_car"), ("doorState", "1", "unlock"), ("doorState", "0", "lock")):
            request = capture(base + action, state=state)
            kind, parsed = control.parse_control_capture(json.dumps(request), STATUS)
            self.assertEqual(kind, expected)
            self.assertEqual(parsed["url"], request["url"])
        for change in ("token", "host", "vehicle"):
            request = capture(base + "findCar")
            if change == "token":
                request["headers"]["access_token"] = "other"
            elif change == "host":
                request["url"] = request["url"].replace("cloudrivechery.mychery.com", "example.com")
            else:
                envelope = json.loads(request["body"])
                envelope["data"] = json.dumps({"vin": "other-car", "userId": "test-user"})
                request["body"] = json.dumps(envelope)
            with self.assertRaises(api.CaptureError):
                control.parse_control_capture(json.dumps(request), STATUS)

    def test_new_status_token_is_carried_to_same_owner_controls(self):
        old = capture("/cheryAppControl/vehicleRemoteControl/vehicleCommand/findCar")
        fresh = {**STATUS, "headers": {**STATUS["headers"], "access_token": "fresh"}}
        updated = control.carry_controls_forward(STATUS, fresh, {"find_car": old})
        self.assertEqual(updated["find_car"]["headers"]["access_token"], "fresh")
        self.assertEqual(updated["find_car"]["body"], old["body"])
        self.assertEqual(old["headers"]["access_token"], "credential")

    def test_wrong_user_discards_commands(self):
        old = capture("/cheryAppControl/vehicleRemoteControl/vehicleCommand/findCar")
        fresh = {**STATUS, "headers": {**STATUS["headers"], "userid": "other-user"}}
        self.assertEqual(control.carry_controls_forward(STATUS, fresh, {"find_car": old}), {})


if __name__ == "__main__":
    unittest.main()
