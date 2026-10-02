"""Import a captured, signed status request without exposing it in logs."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CaptureAuthError, CaptureError, fetch_vehicle_status, parse_capture
from .control import carry_controls_forward, parse_control_capture
from .const import (
    CONF_CAPTURE,
    CONF_CONTROLS,
    DOMAIN,
)

CONF_REQUEST_JSON = "request_json"
CONF_FIND_CAR_JSON = "find_car_json"
CONF_UNLOCK_JSON = "unlock_json"
CONF_LOCK_JSON = "lock_json"
CONTROL_INPUTS = {
    CONF_FIND_CAR_JSON: "find_car",
    CONF_UNLOCK_JSON: "unlock",
    CONF_LOCK_JSON: "lock",
}


def _updated_data(entry: ConfigEntry, capture: dict[str, Any]) -> dict[str, Any]:
    """Carry same-vehicle controls to the newly imported credential."""
    previous = entry.data[CONF_CAPTURE]
    controls = carry_controls_forward(previous, capture, entry.data.get(CONF_CONTROLS, {}))
    return {**entry.data, CONF_CAPTURE: capture, CONF_CONTROLS: controls}


class CheryArrizo8ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one Chery vehicle from a local capture."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CheryArrizo8OptionsFlow:
        """Let the owner replace the captured request from Configure."""
        return CheryArrizo8OptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Import a read-only request."""
        errors = {}
        if user_input is not None:
            try:
                capture = parse_capture(user_input[CONF_REQUEST_JSON])
            except CaptureError:
                errors["base"] = "invalid_capture"
            else:
                try:
                    await fetch_vehicle_status(async_get_clientsession(self.hass), capture)
                except CaptureAuthError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    identifier = hashlib.sha256(capture["url"].encode()).hexdigest()
                    await self.async_set_unique_id(identifier)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="艾瑞泽8", data={CONF_CAPTURE: capture})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_REQUEST_JSON): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Replace an expired captured request."""
        errors = {}
        if user_input is not None:
            try:
                capture = parse_capture(user_input[CONF_REQUEST_JSON])
            except CaptureError:
                errors["base"] = "invalid_capture"
            else:
                try:
                    await fetch_vehicle_status(async_get_clientsession(self.hass), capture)
                except CaptureAuthError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    identifier = hashlib.sha256(capture["url"].encode()).hexdigest()
                    await self.async_set_unique_id(identifier)
                    self._abort_if_unique_id_mismatch()
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data_updates=_updated_data(self._get_reconfigure_entry(), capture),
                    )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_REQUEST_JSON): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Start HA's reauthentication flow after a rejected credential."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Import a fresh request for the same vehicle and reload the entry."""
        errors = {}
        if user_input is not None:
            try:
                capture = parse_capture(user_input[CONF_REQUEST_JSON])
            except CaptureError:
                errors["base"] = "invalid_capture"
            else:
                identifier = hashlib.sha256(capture["url"].encode()).hexdigest()
                await self.async_set_unique_id(identifier)
                self._abort_if_unique_id_mismatch()
                try:
                    await fetch_vehicle_status(async_get_clientsession(self.hass), capture)
                except CaptureAuthError:
                    errors["base"] = "invalid_auth"
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data_updates=_updated_data(self._get_reauth_entry(), capture),
                    )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_REQUEST_JSON): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}),
            errors=errors,
        )


class CheryArrizo8OptionsFlow(OptionsFlow):
    """Replace status or import an explicit control request."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            status_raw = user_input.get(CONF_REQUEST_JSON)
            capture = self.config_entry.data[CONF_CAPTURE]
            if status_raw:
                try:
                    capture = parse_capture(status_raw)
                except CaptureError:
                    errors["base"] = "invalid_capture"
            if not errors and status_raw:
                identifier = hashlib.sha256(capture["url"].encode()).hexdigest()
                if identifier != self.config_entry.unique_id:
                    errors["base"] = "different_vehicle"
                else:
                    try:
                        await fetch_vehicle_status(async_get_clientsession(self.hass), capture)
                    except CaptureAuthError:
                        errors["base"] = "invalid_auth"
                    except Exception:
                        errors["base"] = "cannot_connect"
            controls = carry_controls_forward(
                self.config_entry.data[CONF_CAPTURE], capture,
                self.config_entry.data.get(CONF_CONTROLS, {}),
            )
            if not errors:
                for field, expected_kind in CONTROL_INPUTS.items():
                    if not user_input.get(field):
                        continue
                    try:
                        kind, command = parse_control_capture(user_input[field], capture)
                        if kind != expected_kind:
                            raise CaptureError("wrong control action")
                    except CaptureError:
                        errors["base"] = "invalid_control_capture"
                        break
                    controls[kind] = command
            if not errors:
                if not status_raw and not any(user_input.get(field) for field in CONTROL_INPUTS):
                    errors["base"] = "nothing_to_update"
                else:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={**self.config_entry.data, CONF_CAPTURE: capture, CONF_CONTROLS: controls},
                    )
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    return self.async_create_entry(data={})
        password = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_REQUEST_JSON): password,
                vol.Optional(CONF_FIND_CAR_JSON): password,
                vol.Optional(CONF_UNLOCK_JSON): password,
                vol.Optional(CONF_LOCK_JSON): password,
            }),
            errors=errors,
        )
