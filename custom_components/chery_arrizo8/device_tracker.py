"""Map location from the same read-only vehicle status response."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import COORDINATE_SYSTEM_GCJ02, DOMAIN
from .location import map_position


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create one GPS tracker for this vehicle."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CheryVehicleTracker(coordinator, entry)])


class CheryVehicleTracker(CoordinatorEntity[DataUpdateCoordinator[dict]], TrackerEntity):
    """Expose validated vehicle coordinates to the HA map."""

    _attr_has_entity_name = True
    _attr_name = "09 位置"
    _attr_icon = "mdi:car-sedan"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: DataUpdateCoordinator[dict], entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.unique_id}_location"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name="奇瑞艾瑞泽8",
            manufacturer="奇瑞汽车",
            model="艾瑞泽8",
        )

    @property
    def available(self) -> bool:
        """Do not display a map marker when the server has no usable fix."""
        return super().available and self._position is not None

    @property
    def _position(self) -> tuple[float, float] | None:
        return map_position(self.coordinator.data, COORDINATE_SYSTEM_GCJ02)

    @property
    def latitude(self) -> float | None:
        position = self._position
        return position[0] if position is not None else None

    @property
    def longitude(self) -> float | None:
        position = self._position
        return position[1] if position is not None else None
