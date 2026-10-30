"""Binary sensors for Gallagher Fence (read-only)."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_STALE_HOURS, DEFAULT_STALE_HOURS
from .coordinator import Energiser, GallagherConfigEntry, GallagherCoordinator, Gateway
from .sensor import energiser_device



async def async_setup_entry(
    hass: HomeAssistant,
    entry: GallagherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for en in coordinator.data.energisers.values():
        entities.append(GatewayConnected(coordinator, en.device_id))
        entities.append(ReadingStale(coordinator, en.device_id))
    async_add_entities(entities)


class _EnBase(CoordinatorEntity[GallagherCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: GallagherCoordinator, en_id: int, key: str) -> None:
        super().__init__(coordinator)
        self._en_id = en_id
        en = coordinator.data.energisers[en_id]
        self._attr_unique_id = f"{en_id}_{key}"
        self._attr_device_info = energiser_device(en, coordinator.farm_id)

    @property
    def _en(self) -> Energiser | None:
        return self.coordinator.data.energisers.get(self._en_id)

    @property
    def available(self) -> bool:
        return super().available and self._en is not None


class GatewayConnected(_EnBase):
    _attr_name = "Gateway connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: GallagherCoordinator, en_id: int) -> None:
        super().__init__(coordinator, en_id, "gateway_connected")

    @property
    def _gw(self) -> Gateway | None:
        en = self._en
        return self.coordinator.data.gateways.get(en.gateway_id) if en and en.gateway_id else None

    @property
    def is_on(self) -> bool | None:
        gw = self._gw
        return None if gw is None else gw.status == "Connected"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        gw = self._gw
        if not gw:
            return None
        return {
            "gateway": gw.device_id,
            "type": gw.kind,
            "firmware": gw.firmware,
            "network": gw.network,
            "last_online": gw.last_online.isoformat() if gw.last_online else None,
        }


class ReadingStale(_EnBase):
    """On (problem) when the cloud hasn't had a fresh reading for a while."""

    _attr_name = "Readings out of date"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: GallagherCoordinator, en_id: int) -> None:
        super().__init__(coordinator, en_id, "reading_stale")

    @property
    def is_on(self) -> bool | None:
        en = self._en
        if not en or not en.reading.timestamp:
            return None
        hours = float(
            self.coordinator.config_entry.options.get(CONF_STALE_HOURS, DEFAULT_STALE_HOURS)
        )
        return dt_util.utcnow() - en.reading.timestamp > timedelta(hours=hours)
