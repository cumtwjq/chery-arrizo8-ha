"""Configure one read-only vehicle from a signed request and optional App renewal."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CaptureAuthError, CaptureError, fetch_vehicle_status, parse_capture, with_access_token
from .app_auth import AppCredentialError, renew_vehicle_token
from .const import CONF_APP_LAST_REFRESH, CONF_APP_REFRESH_TOKEN, CONF_CAPTURE, DOMAIN

CONF_REQUEST_JSON = "request_json"

FORM_SCHEMA = vol.Schema({
    vol.Optional(CONF_REQUEST_JSON): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    ),
    vol.Optional(CONF_APP_REFRESH_TOKEN): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    ),
})


async def _validate(
    hass, user_input: dict[str, Any], existing: Mapping[str, Any] | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate imports without replacing a working entry on failure."""
    raw_capture = str(user_input.get(CONF_REQUEST_JSON) or "").strip()
    raw_refresh = str(user_input.get(CONF_APP_REFRESH_TOKEN) or "").strip()
    if not raw_capture and not raw_refresh:
        return None, "missing_input"
    try:
        capture = parse_capture(raw_capture) if raw_capture else dict(existing[CONF_CAPTURE])
    except (CaptureError, KeyError, TypeError):
        return None, "invalid_capture"

    refresh = raw_refresh or (existing.get(CONF_APP_REFRESH_TOKEN, "") if existing else "")
    data = dict(existing or {})
    session = async_get_clientsession(hass)
    if refresh:
        try:
            refresh, vehicle_token = await renew_vehicle_token(session, refresh)
            capture = with_access_token(capture, vehicle_token)
        except AppCredentialError:
            return None, "invalid_refresh"
        except Exception:
            return None, "cannot_connect"
        data[CONF_APP_REFRESH_TOKEN] = refresh
        data[CONF_APP_LAST_REFRESH] = datetime.now(timezone.utc).isoformat()

    try:
        await fetch_vehicle_status(session, capture)
    except CaptureAuthError:
        return None, "invalid_auth"
    except Exception:
        return None, "cannot_connect"
    data[CONF_CAPTURE] = capture
    return data, None


def _vehicle_id(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(data[CONF_CAPTURE]["url"].encode()).hexdigest()


class CheryArrizo8ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a vehicle using the owner's own signed read-only request."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CheryArrizo8OptionsFlow:
        return CheryArrizo8OptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            data, error = await _validate(self.hass, user_input)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(_vehicle_id(data))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="艾瑞泽8", data=data)
        return self.async_show_form(step_id="user", data_schema=FORM_SCHEMA, errors=errors)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            data, error = await _validate(self.hass, user_input, self._get_reconfigure_entry().data)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(_vehicle_id(data))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(self._get_reconfigure_entry(), data_updates=data)
        return self.async_show_form(step_id="reconfigure", data_schema=FORM_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            data, error = await _validate(self.hass, user_input, self._get_reauth_entry().data)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(_vehicle_id(data))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        return self.async_show_form(step_id="reauth_confirm", data_schema=FORM_SCHEMA, errors=errors)


class CheryArrizo8OptionsFlow(OptionsFlow):
    """Update the refresh credential or signed request independently."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors = {}
        if user_input is not None:
            data, error = await _validate(self.hass, user_input, self.config_entry.data)
            if error:
                errors["base"] = error
            elif _vehicle_id(data) != self.config_entry.unique_id:
                errors["base"] = "different_vehicle"
            else:
                self.hass.config_entries.async_update_entry(self.config_entry, data=data)
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(data={})
        return self.async_show_form(step_id="init", data_schema=FORM_SCHEMA, errors=errors)
