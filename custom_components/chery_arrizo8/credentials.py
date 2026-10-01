"""Read token expiry metadata without exposing the credential."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta, timezone
import json


WARNING_BEFORE_EXPIRY = timedelta(days=2)


def token_expiry(capture: dict) -> datetime | None:
    """Return the JWT's declared expiry, if present."""
    try:
        token = next(value for key, value in capture["headers"].items() if key.lower() == "access_token")
        payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "==="))
        return datetime.fromtimestamp(int(payload["exp"]), timezone.utc)
    except (KeyError, StopIteration, IndexError, ValueError, TypeError, OverflowError, binascii.Error):
        return None


def expires_soon(capture: dict, now: datetime | None = None) -> bool:
    """Whether the declared expiry is at most two days away."""
    expiry = token_expiry(capture)
    return expiry is not None and expiry - (now or datetime.now(timezone.utc)) <= WARNING_BEFORE_EXPIRY
