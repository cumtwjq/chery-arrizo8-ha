"""Record only vehicle status field names and value types for local development."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


DESTINATION = Path(os.environ["LOCALAPPDATA"]) / "Arrizo8HA" / "status-shape.json"
DIAGNOSTIC = DESTINATION.with_name("status-diagnostic.json")
_FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,48}$")
_saved = False
_diagnostic: dict[str, object] = {"chery_hosts": [], "status_request_seen": False}


def _write_diagnostic() -> None:
    DIAGNOSTIC.parent.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC.write_text(json.dumps(_diagnostic, ensure_ascii=False), encoding="utf-8")


def request(flow) -> None:
    """Track only Chery hostnames and whether the status endpoint was reached."""
    url = urlsplit(flow.request.pretty_url)
    host = url.hostname or ""
    if not (host.endswith(".mychery.com") or host.endswith(".chery.cn")):
        return
    hosts = _diagnostic["chery_hosts"]
    if host not in hosts:
        hosts.append(host)
    if host == "cloudrivechery.mychery.com" and url.path.startswith(
        "/cheryAppData/vehicleRealtimeData/"
    ):
        _diagnostic["status_request_seen"] = True
    _write_diagnostic()


def _kind(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number" if math.isfinite(float(value)) else "invalid_number"
    if isinstance(value, str):
        try:
            return "numeric_text" if math.isfinite(float(value)) else "text"
        except ValueError:
            return "text"
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    return "other"


def response(flow) -> None:
    """Save a value-free schema from one successful vehicle status reply."""
    global _saved
    if _saved or flow.response is None or flow.response.status_code != 200:
        return
    url = urlsplit(flow.request.pretty_url)
    if url.hostname != "cloudrivechery.mychery.com" or not url.path.startswith(
        "/cheryAppData/vehicleRealtimeData/"
    ):
        return
    _diagnostic["status_response_code"] = flow.response.status_code
    _write_diagnostic()
    try:
        envelope = json.loads(flow.response.raw_content)
        body = envelope["data"]
        status = json.loads(body) if isinstance(body, str) else body
        if not isinstance(status, dict):
            return
        shape = {
            key: _kind(value)
            for key, value in status.items()
            if isinstance(key, str) and _FIELD_NAME.fullmatch(key)
        }
        if not shape:
            return
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION.write_text(json.dumps(shape, ensure_ascii=False, indent=2), encoding="utf-8")
        _diagnostic["status_fields"] = len(shape)
        _write_diagnostic()
        _saved = True
    except (KeyError, TypeError, ValueError, OverflowError):
        _diagnostic["status_parse_failed"] = True
        _write_diagnostic()
        return
