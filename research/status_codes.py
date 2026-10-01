"""Capture only small vehicle state codes, never credentials or location."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

DESTINATION = Path(os.environ["LOCALAPPDATA"]) / "Arrizo8HA" / "status-codes.json"
FIELDS = frozenset({
    "doorLock", "trunkLock", "frontLeftDoor", "frontRightDoor",
    "backLeftDoor", "backRightDoor", "trunkDoor", "hood",
    "frontLeftWindowState", "frontRightWindowState",
    "backLeftWindowState", "backRightWindowState",
    "sunroofState", "sunroofOperateState", "airState", "airPur",
    "engineState", "online", "lAreaTemp", "rAreaTemp",
})


def small_code(value: object) -> str | None:
    """Keep only short numeric codes; reject text that may be personal data."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(number) or abs(number) > 1000:
        return None
    return str(value)[:12]


def response(flow) -> None:
    """Save a sanitized snapshot of a successful read-only status response."""
    url = urlsplit(flow.request.pretty_url)
    if (
        url.hostname != "cloudrivechery.mychery.com"
        or not url.path.startswith("/cheryAppData/vehicleRealtimeData/")
        or flow.response is None
        or flow.response.status_code != 200
    ):
        return
    try:
        envelope = json.loads(flow.response.raw_content)
        data = envelope["data"]
        status = json.loads(data) if isinstance(data, str) else data
        if not isinstance(status, dict):
            return
        codes = {
            key: code for key in FIELDS
            if (code := small_code(status.get(key))) is not None
        }
        if not codes:
            return
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION.write_text(json.dumps({
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "codes": codes,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except (KeyError, TypeError, ValueError, OverflowError):
        return
