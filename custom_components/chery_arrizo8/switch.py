"""Vehicle lock switch backed by observed status and two captured commands."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import ClientError

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import CaptureError
from .const import CONF_CAPTURE, CONF_CONTROLS, DOMAIN
from .control import _header, _vehicle, send_control
from .credentials import token_expiry


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Expose one switch only after both commands have been imported."""
    controls = entry.data.get(CONF_CONTROLS, {})
    if "lock" in controls and "unlock" in controls:
        async_add_entities([CheryLockSwitch(hass, entry)])


class CheryLockSwitch(CoordinatorEntity, SwitchEntity):
    """On means locked; off means unlocked, from vehicle status only."""

    _attr_has_entity_name = True
    _attr_name = "车锁控制（实验）"
    _attr_icon = "mdi:car-door-lock"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass.data[DOMAIN][entry.entry_id])
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry.unique_id}_lock_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="奇瑞艾瑞泽8", manufacturer="奇瑞汽车", model="艾瑞泽8",
        )
        self._operation_lock = asyncio.Lock()
        self._last_command: datetime | None = None

    @property
    def available(self) -> bool:
        status = self.entry.data[CONF_CAPTURE]
        controls = self.entry.data.get(CONF_CONTROLS, {})
        if str(self.coordinator.data.get("doorLock", "")) not in ("0", "1"):
            return False
        expiry = token_expiry(status)
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            return False
        try:
            return all(
                _header(controls[kind], "access_token") == _header(status, "access_token")
                and _vehicle(controls[kind]) == _vehicle(status)
                for kind in ("lock", "unlock")
            )
        except (KeyError, TypeError, ValueError):
            return False

    @property
    def is_on(self) -> bool | None:
        value = str(self.coordinator.data.get("doorLock", ""))
        return {"0": True, "1": False}.get(value)

    async def async_turn_on(self, **kwargs) -> None:
        """Lock only when fresh status still reports unlocked."""
        await self._operate("lock", "1")

    async def async_turn_off(self, **kwargs) -> None:
        """Unlock only when fresh status still reports locked."""
        await self._operate("unlock", "0")

    async def _operate(self, kind: str, expected: str) -> None:
        async with self._operation_lock:
            if not self.available:
                raise HomeAssistantError("车锁状态或控制请求不可用，请更新车况及登录凭证")
            now = datetime.now(timezone.utc)
            if self._last_command and now - self._last_command < timedelta(seconds=60):
                raise HomeAssistantError("请至少等待 60 秒再操作车锁")
            try:
                await self.coordinator.async_request_refresh()
            except Exception as err:
                raise HomeAssistantError("无法确认当前车锁状态，未发送控制命令") from err
            fetched_at = self.coordinator.data.get("_ha_last_successful_fetch")
            if (not self.coordinator.last_update_success or not isinstance(fetched_at, datetime)
                    or datetime.now(timezone.utc) - fetched_at > timedelta(minutes=2)):
                raise HomeAssistantError("车况刷新失败，未发送车锁命令")
            observed = str(self.coordinator.data.get("doorLock", ""))
            if observed != expected:
                if observed in ("0", "1"):
                    return  # Already in the requested state.
                raise HomeAssistantError("当前车锁状态未知，未发送控制命令")
            self._last_command = datetime.now(timezone.utc)
            try:
                await send_control(async_get_clientsession(self.hass), self.entry.data[CONF_CONTROLS][kind])
            except (CaptureError, ClientError, TimeoutError) as err:
                raise HomeAssistantError("车锁命令未获服务器确认；请在 App 核对状态后再操作") from err
            await asyncio.sleep(5)
            try:
                await self.coordinator.async_request_refresh()
            except Exception:
                # The command was accepted; HA keeps the last observed state.
                pass
            self.async_write_ha_state()
