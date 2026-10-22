"""Read-only vehicle status for the Chinese Chery app."""

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

from .api import CaptureAuthError, CaptureError, fetch_vehicle_status, with_access_token
from .app_auth import AppCredentialError, AppTokenError, renew_vehicle_token
from .const import CONF_APP_LAST_REFRESH, CONF_APP_REFRESH_TOKEN, CONF_CAPTURE, DOMAIN, POLL_MINUTES
from .credentials import WARNING_BEFORE_EXPIRY, token_expiry
from .renewal import renewal_due

PLATFORMS = ["sensor", "device_tracker"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one vehicle."""
    session = async_get_clientsession(hass)
    state = dict(entry.data)
    normal_interval = timedelta(minutes=POLL_MINUTES)

    async def renew() -> None:
        """Save a rotated App credential together with its new vehicle token."""
        refresh, vehicle_token = await renew_vehicle_token(session, state[CONF_APP_REFRESH_TOKEN])
        state.update({
            CONF_CAPTURE: with_access_token(state[CONF_CAPTURE], vehicle_token),
            CONF_APP_REFRESH_TOKEN: refresh,
            CONF_APP_LAST_REFRESH: datetime.now(timezone.utc).isoformat(),
        })
        hass.config_entries.async_update_entry(entry, data=dict(state))

    async def update() -> dict:
        try:
            renewed = False
            if renewal_due(state):
                await renew()
                renewed = True
            try:
                status = await fetch_vehicle_status(session, state[CONF_CAPTURE])
            except CaptureAuthError as err:
                if not state.get(CONF_APP_REFRESH_TOKEN):
                    raise ConfigEntryAuthFailed("奇瑞车况登录凭证已被拒绝，请更新车况请求") from err
                if renewed:
                    raise ConfigEntryAuthFailed("车况令牌已更新，但签名请求仍被拒绝，请重新抓取车况请求") from err
                await renew()
                try:
                    status = await fetch_vehicle_status(session, state[CONF_CAPTURE])
                except CaptureAuthError as retry_err:
                    raise ConfigEntryAuthFailed("车况令牌已更新，但签名请求仍被拒绝，请重新抓取车况请求") from retry_err
        except AppCredentialError as err:
            raise ConfigEntryAuthFailed("奇瑞 App 刷新凭证已失效，请更新") from err
        except AppTokenError as err:
            raise UpdateFailed("奇瑞 App 暂未返回新的车况令牌") from err
        except ClientResponseError as err:
            if err.status == 429:
                coordinator.update_interval = timedelta(hours=1)
                raise UpdateFailed("奇瑞接口返回限流，自动查询暂停约一小时") from err
            raise UpdateFailed(f"奇瑞车况服务器返回 HTTP {err.status}") from err
        except (ClientError, asyncio.TimeoutError) as err:
            raise UpdateFailed("无法连接奇瑞车况服务器，请检查网络") from err
        except CaptureError as err:
            raise UpdateFailed("奇瑞车况响应无效，请稍后重试") from err
        if coordinator.update_interval != normal_interval:
            coordinator.update_interval = normal_interval
        status["_ha_last_successful_fetch"] = datetime.now(timezone.utc)
        return status

    coordinator = DataUpdateCoordinator(
        hass,
        logger=_LOGGER,
        name=DOMAIN,
        update_method=update,
        update_interval=normal_interval,
    )
    await coordinator.async_config_entry_first_refresh()
    if state.get(CONF_APP_REFRESH_TOKEN):
        ir.async_delete_issue(hass, DOMAIN, f"credential_expiring_{entry.entry_id}")
    else:
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
