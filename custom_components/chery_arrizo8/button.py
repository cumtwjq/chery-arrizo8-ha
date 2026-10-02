"""Manual vehicle commands. Each press sends at most one captured request."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiohttp import ClientError

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CaptureError
from .const import CONF_CAPTURE, CONF_CONTROLS, DOMAIN
from .control import _header, _vehicle, send_control
from .credentials import token_expiry


NAMES = {"find_car": "寻车闪灯（实验）"}
ICONS = {"find_car": "mdi:car-light-high"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    controls = entry.data.get(CONF_CONTROLS, {})
    async_add_entities([CheryControlButton(hass, entry, "find_car")] if "find_car" in controls else [])


class CheryControlButton(ButtonEntity):
    """A user-triggered command; no automatic retries or background execution."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, kind: str) -> None:
        self.hass = hass
        self.entry = entry
        self.kind = kind
        self._last_press: datetime | None = None
        self._attr_name = NAMES[kind]
        self._attr_icon = ICONS[kind]
        self._attr_unique_id = f"{entry.unique_id}_{kind}_button"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="奇瑞艾瑞泽8", manufacturer="奇瑞汽车", model="艾瑞泽8",
        )

    @property
    def available(self) -> bool:
        """Refuse use after a credential or vehicle mismatch."""
        status = self.entry.data[CONF_CAPTURE]
        control = self.entry.data.get(CONF_CONTROLS, {}).get(self.kind)
        if not control or _header(control, "access_token") != _header(status, "access_token"):
            return False
        expiry = token_expiry(status)
        if expiry is not None and expiry <= datetime.now(timezone.utc):
            return False
        try:
            return _vehicle(control) == _vehicle(status)
        except (KeyError, TypeError, ValueError):
            return False

    async def async_press(self) -> None:
        if not self.available:
            raise HomeAssistantError("控制请求已失效，请重新抓取并导入")
        now = datetime.now(timezone.utc)
        if self._last_press and now - self._last_press < timedelta(seconds=60):
            raise HomeAssistantError("请至少等待 60 秒再操作车辆")
        # Set before network I/O so a timeout cannot cause an immediate duplicate command.
        self._last_press = now
        try:
            await send_control(async_get_clientsession(self.hass), self.entry.data[CONF_CONTROLS][self.kind])
        except (CaptureError, ClientError, TimeoutError) as err:
            raise HomeAssistantError("控制请求未获服务器确认；请在 App 核对车辆状态后再操作") from err
        self.async_write_ha_state()
