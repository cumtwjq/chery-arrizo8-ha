"""mitmproxy addon: save one successful, read-only Chery status request.

The request is encrypted with Windows DPAPI. No token, VIN, location, or
response body is written to the console or marker file.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

from vault import VAULT, load_capture, save_capture


READY_MARKER = VAULT.with_name("capture-ready.json")
_captured = False


def _token(headers: dict[str, str]) -> str | None:
    return next((value for key, value in headers.items() if key.lower() == "access_token"), None)


def _expiry(token: str | None) -> str | None:
    if not token:
        return None
    try:
        encoded = token.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(encoded + "==="))
        return datetime.fromtimestamp(int(payload["exp"]), timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    except (IndexError, KeyError, TypeError, ValueError, OverflowError):
        return None


def _validated_capture(flow) -> dict | None:
    request = flow.request
    response = flow.response
    url = urlsplit(request.pretty_url)
    if (
        request.method != "POST"
        or url.scheme != "https"
        or url.hostname != "cloudrivechery.mychery.com"
        or url.port not in (None, 443)
        or not url.path.startswith("/cheryAppData/vehicleRealtimeData/")
        or url.query
        or response is None
        or response.status_code != 200
    ):
        return None
    try:
        raw_body = request.raw_content.decode("utf-8")
        body = json.loads(raw_body)
        inner = json.loads(body["data"])
        payload = json.loads(response.raw_content)
        status = json.loads(payload["data"])
        if not isinstance(inner.get("vin"), str) or not isinstance(status, dict):
            return None
        if "odometer" not in status and "mileageSurplus" not in status:
            return None
        if not all(isinstance(body.get(key), str) for key in ("sign", "requestId", "appId", "version")):
            return None
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() in {"access_token", "userid", "content-type", "timestamp", "x-sermant-group"}
        }
        if not _token(headers):
            return None
        return {"url": request.pretty_url, "headers": headers, "body": raw_body}
    except (KeyError, TypeError, ValueError, UnicodeDecodeError):
        return None


def response(flow) -> None:
    """Accept only a successful vehicle-status call from this owner session."""
    global _captured
    if _captured:
        return
    capture = _validated_capture(flow)
    if capture is None:
        return
    previous_token = None
    try:
        previous_token = _token(load_capture()["headers"])
    except (OSError, KeyError, ValueError):
        pass
    save_capture(capture)
    token = _token(capture["headers"])
    marker = {
        "captured_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "token_changed": previous_token is None or previous_token != token,
        "token_expires_at": _expiry(token),
    }
    READY_MARKER.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    _captured = True
