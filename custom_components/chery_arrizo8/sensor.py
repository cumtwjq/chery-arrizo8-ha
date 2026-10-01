"""Conservative sensors from the verified status response."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import CONF_CAPTURE, DOMAIN
from .credentials import token_expiry
from .measurement import UNITS, numeric_value
from .status_fields import ACTIVE_FIELDS, display_status_value, ordered_label, safe_status_fields


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Add only fields actually present for this vehicle."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    registry = er.async_get(hass)
    prefix = f"{entry.unique_id}_"
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registered.domain == "sensor"
            and registered.platform == DOMAIN
            and registered.unique_id.startswith(prefix)
            and registered.unique_id.removeprefix(prefix) not in ACTIVE_FIELDS | {"token_expiry", "last_successful_fetch"}
        ):
            registry.async_remove(registered.entity_id)
    entities = [
        CheryStatusSensor(coordinator, entry, key, label)
        for key, label in safe_status_fields(coordinator.data)
        if key in ACTIVE_FIELDS
    ]
    expires_at = token_expiry(entry.data[CONF_CAPTURE])
    if expires_at is not None:
        entities.append(CheryTokenExpirySensor(entry, expires_at))
    entities.append(CheryLastSuccessfulFetchSensor(coordinator, entry))
    async_add_entities(entities)


class CheryTokenExpirySensor(SensorEntity):
    """Display the token's declared expiration, regardless of vehicle polling."""

    _attr_has_entity_name = True
    _attr_name = "02 登录凭证到期时间"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: ConfigEntry, expires_at: datetime) -> None:
        self._attr_unique_id = f"{entry.unique_id}_token_expiry"
        self._attr_native_value = expires_at
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="奇瑞艾瑞泽8",
            manufacturer="奇瑞汽车",
            model="艾瑞泽8",
        )


class CheryLastSuccessfulFetchSensor(CoordinatorEntity[DataUpdateCoordinator[dict]], SensorEntity):
    """Keep the last successful HA fetch visible during later API failures."""

    _attr_has_entity_name = True
    _attr_name = "03 HA 上次成功读取时间"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: DataUpdateCoordinator[dict], entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_last_successful_fetch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="奇瑞艾瑞泽8",
            manufacturer="奇瑞汽车",
            model="艾瑞泽8",
        )

    @property
    def available(self) -> bool:
        """Show the cached timestamp even when the latest API poll failed."""
        return self.native_value is not None

    @property
    def native_value(self) -> datetime | None:
        """Return the successful fetch time, not the vehicle report time."""
        value = self.coordinator.data.get("_ha_last_successful_fetch")
        return value if isinstance(value, datetime) else None


class CheryStatusSensor(CoordinatorEntity[DataUpdateCoordinator[dict]], SensorEntity):
    """One unmodified field from the app's status response."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator[dict], entry: ConfigEntry, key: str, label: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = ordered_label(key, label)
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_native_unit_of_measurement = UNITS.get(key)
        if key in UNITS:
            self._attr_suggested_display_precision = 0
        if key in ("odometer", "mileageSurplus"):
            self._attr_device_class = SensorDeviceClass.DISTANCE
        elif key.endswith("TyrekPa"):
            self._attr_device_class = SensorDeviceClass.PRESSURE
        elif key in ("lAreaTemp", "rAreaTemp"):
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="奇瑞艾瑞泽8",
            manufacturer="奇瑞汽车",
            model="艾瑞泽8",
        )

    @property
    def native_value(self) -> str | int | float | None:
        """Keep state codes raw and expose measurements as numeric values."""
        value = self.coordinator.data.get(self._key)
        value = display_status_value(self._key, value)
        if self._key in UNITS:
            return numeric_value(value)
        if isinstance(value, str):
            number = numeric_value(value)
            return number if number is not None else value
        return value if isinstance(value, (str, int, float)) else None
