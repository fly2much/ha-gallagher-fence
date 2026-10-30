"""Gallagher Fence (read-only) - energiser, zone and earth readings from the Gallagher cloud."""
from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GallagherApi
from .const import CONF_REFRESH_TOKEN
from .coordinator import GallagherConfigEntry, GallagherCoordinator

# Deliberately no switch/button platforms: this integration never controls the fence.
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: GallagherConfigEntry) -> bool:
    api = GallagherApi(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_REFRESH_TOKEN),
    )
    coordinator = GallagherCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GallagherConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
