"""mitmproxy addon for one successful, user-triggered Chery command."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from urllib.parse import urlsplit

from vault import CONTROL_KINDS, control_vault, load_capture, save_control


KIND = os.environ.get("ARRIZO8_CONTROL_KIND")
if KIND not in CONTROL_KINDS:
    raise RuntimeError("select exactly one control kind")
COMMANDS = {"find_car": ("findCar", None), "unlock": ("doorState", "1"), "lock": ("doorState", "0")}
READY_MARKER = control_vault(KIND).with_suffix(".ready.json")
_captured = False


def _header(headers, name: str) -> str | None:
    return next((str(value) for key, value in headers.items() if key.lower() == name), None)


def _capture(flow) -> dict | None:
    request, response = flow.request, flow.response
    url = urlsplit(request.pretty_url)
    expected_path = "/cheryAppControl/vehicleRemoteControl/vehicleCommand/" + COMMANDS[KIND][0]
    if (request.method != "POST" or url.scheme != "https" or
            url.hostname != "cloudrivechery.mychery.com" or url.port not in (None, 443) or
            url.path != expected_path or url.query or response is None or response.status_code != 200):
        return None
    try:
        status_capture = load_capture()
        raw = request.raw_content.decode("utf-8")
        envelope = json.loads(raw)
        inner = json.loads(envelope["data"])
        status_inner = json.loads(json.loads(status_capture["body"])["data"])
        response_data = json.loads(response.raw_content)
        result = json.loads(response_data["data"])
        if str(response_data.get("resultCode")) != "200" or not result.get("seq"):
            return None
        if inner.get("vin") != status_inner.get("vin"):
            return None
        if _header(request.headers, "access_token") != _header(status_capture["headers"], "access_token"):
            return None
        if _header(request.headers, "userid") != _header(status_capture["headers"], "userid"):
            return None
        if str(inner.get("userId")) != _header(request.headers, "userid"):
            return None
        if KIND == "find_car":
            if set(inner) != {"userId", "vin"}:
                return None
        elif set(inner) != {"doorState", "userId", "vin"} or inner["doorState"] != COMMANDS[KIND][1]:
            return None
        if not all(isinstance(envelope.get(key), str) for key in ("appId", "data", "requestId", "sign", "version")):
            return None
        headers = {key: value for key, value in request.headers.items() if key.lower() in
                   {"access_token", "userid", "content-type", "timestamp", "x-sermant-group"}}
        return {"url": request.pretty_url, "headers": headers, "body": raw}
    except (OSError, KeyError, TypeError, ValueError, UnicodeDecodeError):
        return None


def response(flow) -> None:
    global _captured
    if _captured:
        return
    capture = _capture(flow)
    if capture is None:
        return
    save_control(KIND, capture)
    READY_MARKER.write_text(json.dumps({
        "captured_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "capture_file_modified_ns": control_vault(KIND).stat().st_mtime_ns,
    }), encoding="utf-8")
    _captured = True
