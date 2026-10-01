"""Only the verified vehicle status endpoint is called."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientSession

from .credentials import token_expiry
from datetime import datetime, timezone


class CaptureError(ValueError):
    """The captured read-only request cannot be used."""


class CaptureAuthError(CaptureError):
    """The status server rejected the captured credential."""


def parse_capture(raw: str) -> dict[str, Any]:
    """Validate an imported request before storing or sending it."""
    try:
        capture = json.loads(raw)
        if not isinstance(capture, dict):
            raise CaptureError("not an object")
        url = capture["url"]
        headers = capture["headers"]
        body = capture["body"]
        parsed_url = urlparse(url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "cloudrivechery.mychery.com"
            or parsed_url.port not in (None, 443)
            or not parsed_url.path.startswith("/cheryAppData/vehicleRealtimeData/")
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise CaptureError("unexpected URL")
        if not isinstance(headers, dict) or not isinstance(body, str):
            raise CaptureError("invalid headers or body")
        envelope = json.loads(body)
        if not isinstance(envelope, dict):
            raise CaptureError("invalid envelope")
        normalized_headers = {
            str(key): str(value)
            for key, value in headers.items()
            if key.lower() in {"access_token", "userid", "content-type", "timestamp", "x-sermant-group"}
        }
        if not any(key.lower() == "access_token" for key in normalized_headers):
            raise CaptureError("missing access_token")
        for key in ("sign", "requestId", "appId", "version", "data"):
            if not isinstance(envelope.get(key), str):
                raise CaptureError("missing envelope field")
        inner = json.loads(envelope["data"])
        if not isinstance(inner, dict) or not isinstance(inner.get("vin"), str):
            raise CaptureError("missing vehicle identifier")
        return {"url": url, "headers": normalized_headers, "body": body}
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as err:
        if isinstance(err, CaptureError):
            raise
        raise CaptureError("invalid capture") from err


async def fetch_vehicle_status(session: ClientSession, capture: dict[str, Any]) -> dict[str, Any]:
    """Fetch status with the known-good signed request; no control commands."""
    async with session.post(
        capture["url"],
        headers=capture["headers"],
        data=capture["body"].encode("utf-8"),
        timeout=20,
    ) as response:
        if response.status in (401, 403):
            raise CaptureAuthError("vehicle status authentication rejected")
        response.raise_for_status()
        try:
            payload = await response.json(content_type=None)
        except (TypeError, ValueError) as err:
            raise CaptureError("vehicle status has unexpected format") from err
    if not isinstance(payload, dict) or not payload.get("data"):
        expiry = token_expiry(capture)
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            raise CaptureAuthError("vehicle status credential expired")
        raise CaptureError("vehicle status unavailable")
    try:
        status = json.loads(payload["data"])
    except (TypeError, ValueError) as err:
        raise CaptureError("vehicle status has unexpected format") from err
    if not isinstance(status, dict):
        raise CaptureError("vehicle status has unexpected format")
    return status
