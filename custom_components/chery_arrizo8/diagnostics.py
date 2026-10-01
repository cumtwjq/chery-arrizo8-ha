"""Safe Home Assistant diagnostics for vehicle field research."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .status_fields import diagnostic_status_shape


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Expose field names, types and simple binary codes, never credentials or GPS."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {"status_fields": diagnostic_status_shape(coordinator.data)}
