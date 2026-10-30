"""Config flow for Gallagher Fence (read-only)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GallagherApi, GallagherApiError, GallagherAuthError
from .const import (
    CONF_FARM_ID,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_MINUTES,
    CONF_STALE_HOURS,
    DEFAULT_SCAN_MINUTES,
    DEFAULT_STALE_HOURS,
    DOMAIN,
)

SCHEMA = vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})


class GallagherFenceConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "GallagherOptionsFlow":
        return GallagherOptionsFlow()

    async def _try_login(self, username: str, password: str) -> tuple[dict[str, str], dict[str, Any]]:
        errors: dict[str, str] = {}
        result: dict[str, Any] = {}
        api = GallagherApi(async_get_clientsession(self.hass), username, password)
        try:
            await api.login()
            farms = await api.farms()
        except GallagherAuthError:
            errors["base"] = "invalid_auth"
        except GallagherApiError:
            errors["base"] = "cannot_connect"
        else:
            if not farms:
                errors["base"] = "no_farm"
            else:
                result = {
                    "farm_id": farms[0]["id"],
                    "farm_name": farms[0].get("name") or "Farm",
                    "refresh_token": api.refresh_token,
                }
        return errors, result

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors, res = await self._try_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            if not errors:
                await self.async_set_unique_id(str(res["farm_id"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Gallagher Fence ({res['farm_name']})",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_FARM_ID: res["farm_id"],
                        CONF_REFRESH_TOKEN: res["refresh_token"],
                    },
                )
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            errors, res = await self._try_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data={
                        **entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_REFRESH_TOKEN: res["refresh_token"],
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                SCHEMA, {CONF_USERNAME: entry.data.get(CONF_USERNAME)}
            ),
            errors=errors,
        )


class GallagherOptionsFlow(OptionsFlowWithReload):
    """Settings you can change from Devices & services -> Gallagher Fence -> Configure."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_MINUTES,
                    default=opts.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                vol.Required(
                    CONF_STALE_HOURS,
                    default=opts.get(CONF_STALE_HOURS, DEFAULT_STALE_HOURS),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=48)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
