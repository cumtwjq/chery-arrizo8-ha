"""Decide when to renew without relying on Home Assistant internals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Any

from .const import CONF_APP_LAST_REFRESH, CONF_APP_REFRESH_TOKEN, CONF_CAPTURE
from .credentials import token_expiry


def renewal_due(data: Mapping[str, Any], now: datetime | None = None) -> bool:
    """Refresh daily, or earlier when the vehicle token is about to expire."""
    if not data.get(CONF_APP_REFRESH_TOKEN):
        return False
    now = now or datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(data.get(CONF_APP_LAST_REFRESH, ""))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        last = datetime.min.replace(tzinfo=timezone.utc)
    expiry = token_expiry(data[CONF_CAPTURE])
    return now - last >= timedelta(days=1) or (
        expiry is not None
        and expiry - now <= timedelta(days=1)
        and now - last >= timedelta(hours=1)
    )
