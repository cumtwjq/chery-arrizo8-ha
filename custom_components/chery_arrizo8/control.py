"""Explicit, single-shot vehicle commands from owner-imported app requests."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientSession

from .api import CaptureError, parse_capture


COMMANDS = {
    "find_car": ("findCar", None),
    "unlock": ("doorState", "1"),
    "lock": ("doorState", "0"),
}


def parse_request_import(raw: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Accept a status request or one owner-owned status/control bundle."""
    try:
        source = json.loads(raw)
    except (TypeError, ValueError) as err:
        raise CaptureError("invalid request JSON") from err
    if not isinstance(source, dict) or "status" not in source:
        return parse_capture(raw), None
    if set(source) != {"status", "controls"} or not isinstance(source["controls"], dict):
        raise CaptureError("invalid request bundle")
    status = parse_capture(json.dumps(source["status"], ensure_ascii=False))
    controls = {}
    for expected_kind, request in source["controls"].items():
        if expected_kind not in COMMANDS:
            raise CaptureError("unsupported bundled command")
        kind, control = parse_control_capture(json.dumps(request, ensure_ascii=False), status)
        if kind != expected_kind:
            raise CaptureError("bundled command mismatch")
        controls[kind] = control
    if not controls:
        raise CaptureError("empty control bundle")
    return status, controls


def _header(capture: dict[str, Any], name: str) -> str | None:
    return next((value for key, value in capture["headers"].items() if key.lower() == name), None)


def _vehicle(capture: dict[str, Any]) -> str:
    return json.loads(json.loads(capture["body"])["data"])["vin"]


def carry_controls_forward(
    previous_status: dict[str, Any], new_status: dict[str, Any], controls: dict[str, Any]
) -> dict[str, Any]:
    """Keep same-owner commands and replace only their credential header."""
    if (_vehicle(previous_status) != _vehicle(new_status) or
            _header(previous_status, "userid") != _header(new_status, "userid")):
        return {}
    token = _header(new_status, "access_token")
    updated = {}
    for kind, control in controls.items():
        if kind not in COMMANDS or _header(control, "access_token") != _header(previous_status, "access_token"):
            continue
        headers = dict(control["headers"])
        original_key = next(key for key in headers if key.lower() == "access_token")
        headers[original_key] = token
        updated[kind] = {**control, "headers": headers}
    return updated


def parse_control_capture(raw: str, status_capture: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Accept only a known control command for the same car and credential."""
    try:
        source = json.loads(raw)
        url = source["url"]
        parsed = urlparse(url)
        if (
            not isinstance(url, str)
            or parsed.scheme != "https"
            or parsed.hostname != "cloudrivechery.mychery.com"
            or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise CaptureError("unexpected control URL")
        path_prefix = "/cheryAppControl/vehicleRemoteControl/vehicleCommand/"
        if not parsed.path.startswith(path_prefix):
            raise CaptureError("unexpected control path")
        command_name = parsed.path[len(path_prefix):]
        if command_name not in {"findCar", "doorState"} or "/" in command_name:
            raise CaptureError("unsupported control command")
        headers = source["headers"]
        body = source["body"]
        if not isinstance(headers, dict) or not isinstance(body, str):
            raise CaptureError("invalid control request")
        capture = {
            "url": url,
            "headers": {str(key): str(value) for key, value in headers.items()
                        if key.lower() in {"access_token", "userid", "content-type", "timestamp", "x-sermant-group"}},
            "body": body,
        }
        if _header(capture, "access_token") != _header(status_capture, "access_token"):
            raise CaptureError("control credential differs from vehicle status")
        if _header(capture, "userid") != _header(status_capture, "userid"):
            raise CaptureError("control user differs from vehicle status")
        envelope = json.loads(body)
        if not all(isinstance(envelope.get(key), str) and envelope[key] for key in
                   ("appId", "data", "requestId", "sign", "version")):
            raise CaptureError("invalid signed control request")
        inner = json.loads(envelope["data"])
        if not isinstance(inner, dict) or inner.get("vin") != _vehicle(status_capture):
            raise CaptureError("control vehicle differs from vehicle status")
        kind = "find_car" if command_name == "findCar" else {"1": "unlock", "0": "lock"}.get(inner.get("doorState"))
        if kind is None:
            raise CaptureError("unsupported lock state")
        expected_state = COMMANDS[kind][1]
        if kind == "find_car":
            if set(inner) != {"userId", "vin"}:
                raise CaptureError("unexpected find-car parameters")
        elif inner.get("doorState") != expected_state or set(inner) != {"doorState", "userId", "vin"}:
            raise CaptureError("unexpected lock parameters")
        if str(inner["userId"]) != _header(capture, "userid"):
            raise CaptureError("control user mismatch")
        return kind, capture
    except (KeyError, TypeError, AttributeError, ValueError, json.JSONDecodeError) as err:
        if isinstance(err, CaptureError):
            raise
        raise CaptureError("invalid control capture") from err


async def send_control(session: ClientSession, capture: dict[str, Any]) -> None:
    """Send exactly one imported command; never retry a physical action."""
    async with session.post(
        capture["url"],
        headers=capture["headers"],
        data=capture["body"].encode("utf-8"),
        timeout=20,
        allow_redirects=False,
    ) as response:
        if response.status != 200:
            raise CaptureError(f"control server returned HTTP {response.status}")
        try:
            payload = await response.json(content_type=None)
        except (TypeError, ValueError) as err:
            raise CaptureError("control server returned invalid JSON") from err
    if not isinstance(payload, dict) or str(payload.get("resultCode")) != "200":
        raise CaptureError("control server did not accept the command")
    try:
        result = json.loads(payload["data"])
    except (KeyError, TypeError, ValueError) as err:
        raise CaptureError("control server did not confirm a sequence") from err
    if not isinstance(result, dict) or not result.get("seq"):
        raise CaptureError("control server did not confirm a sequence")
