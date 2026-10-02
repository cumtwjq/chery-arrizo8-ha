"""Vehicle status and explicitly imported experimental commands."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging

from aiohttp import ClientError, ClientResponseError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CaptureAuthError, CaptureError, fetch_vehicle_status
from .const import CONF_CAPTURE, DOMAIN, POLL_MINUTES
from .credentials import WARNING_BEFORE_EXPIRY, token_expiry

PLATFORMS = ["sensor", "device_tracker", "button", "switch"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one vehicle."""
    session = async_get_clientsession(hass)

    async def update() -> dict:
        try:
            status = await fetch_vehicle_status(session, entry.data[CONF_CAPTURE])
        except CaptureAuthError as err:
            raise ConfigEntryAuthFailed("奇瑞车况登录凭证已被拒绝，请更新车况请求") from err
        except ClientResponseError as err:
            raise UpdateFailed(f"奇瑞车况服务器返回 HTTP {err.status}") from err
        except (ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed("无法连接奇瑞车况服务器，请检查网络") from err
        except CaptureError as err:
            raise UpdateFailed("奇瑞车况响应无效，请稍后重试") from err
        status["_ha_last_successful_fetch"] = datetime.now(timezone.utc)
        return status

    coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name=DOMAIN,
        update_method=update,
        update_interval=timedelta(minutes=POLL_MINUTES),
    )
    await coordinator.async_config_entry_first_refresh()
    _schedule_expiry_warning(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _schedule_expiry_warning(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise a Repairs warning when the captured JWT has two days left."""
    issue_id = f"credential_expiring_{entry.entry_id}"
    expiry = token_expiry(entry.data[CONF_CAPTURE])
    if expiry is None:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    def warn(_now: datetime | None = None) -> None:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="credential_expiring",
            translation_placeholders={"expiry": expiry.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M") + "（北京时间）"},
        )

    warning_time = expiry - WARNING_BEFORE_EXPIRY
    if warning_time <= datetime.now(timezone.utc):
        warn()
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        entry.async_on_unload(async_track_point_in_utc_time(hass, warn, warning_time))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the vehicle."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
