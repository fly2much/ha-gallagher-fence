"""Sensors for Gallagher Fence (read-only)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Energiser, GallagherConfigEntry, GallagherCoordinator, Zone


def energiser_device(en: Energiser, farm_id: int) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"energiser_{en.device_id}")},
        name=en.name,
        manufacturer="Gallagher",
        model=en.model or "Energiser",
        serial_number=en.serial,
        sw_version=en.firmware,
    )


def zone_label(z: Zone) -> str:
    if z.kind == "Earth":
        return "Earth"
    if z.number is not None and not z.name.strip().startswith(str(z.number)):
        return f"{z.number} - {z.name}"
    return z.name


def _milli(key: str) -> Callable[[Energiser], float | None]:
    def fn(en: Energiser) -> float | None:
        v = en.reading.extra.get(key)
        return round(v / 1000, 2) if isinstance(v, (int, float)) else None

    return fn


def _extra(key: str) -> Callable[[Energiser], Any]:
    return lambda en: en.reading.extra.get(key)


@dataclass(frozen=True, kw_only=True)
class EnergiserSensorDescription(SensorEntityDescription):
    value_fn: Callable[[Energiser], Any]
    needs_extra: str | None = None


ENERGISER_SENSORS: tuple[EnergiserSensorDescription, ...] = (
    EnergiserSensorDescription(
        key="fence_voltage",
        name="Fence voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.KILOVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda en: en.reading.voltage,
    ),
    EnergiserSensorDescription(
        key="fence_current",
        name="Fence current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda en: en.reading.current,
    ),
    EnergiserSensorDescription(
        key="last_reading",
        name="Last reading",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda en: en.reading.timestamp,
    ),
    EnergiserSensorDescription(
        key="status",
        name="Status",
        icon="mdi:fence-electric",
        value_fn=lambda en: en.status,
    ),
    EnergiserSensorDescription(
        key="battery_status",
        name="Battery status",
        icon="mdi:battery-check",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda en: en.battery,
    ),
    # Extra telemetry only some models (e.g. MB2800i on the App Gateway) report.
    EnergiserSensorDescription(
        key="battery_voltage",
        name="Battery voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        needs_extra="battVltBeforeChrg",
        value_fn=_milli("battVltBeforeChrg"),
    ),
    EnergiserSensorDescription(
        key="supply_voltage",
        name="Supply voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        needs_extra="recentDcVlt",
        value_fn=_milli("recentDcVlt"),
    ),
    EnergiserSensorDescription(
        key="ambient_temperature",
        name="Energiser temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        needs_extra="ambientTemp",
        value_fn=_extra("ambientTemp"),
    ),
    EnergiserSensorDescription(
        key="fence_voltage_min",
        name="Fence voltage (period low)",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.KILOVOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        needs_extra="voltageMin",
        value_fn=_extra("voltageMin"),
    ),
    EnergiserSensorDescription(
        key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=0,
        entity_category=EntityCategory.DIAGNOSTIC,
        needs_extra="uptime",
        value_fn=_extra("uptime"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GallagherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [AlertsSensor(coordinator)]
    for en in coordinator.data.energisers.values():
        for desc in ENERGISER_SENSORS:
            if desc.needs_extra and desc.needs_extra not in en.reading.extra:
                continue
            entities.append(EnergiserSensor(coordinator, en.device_id, desc))
        for z in sorted(en.zones.values(), key=lambda z: (z.kind != "Earth", z.number or 0)):
            entities.append(ZoneSensor(coordinator, en.device_id, z.device_id, "voltage"))
            entities.append(ZoneSensor(coordinator, en.device_id, z.device_id, "current"))
    async_add_entities(entities)


class _Base(CoordinatorEntity[GallagherCoordinator]):
    _attr_has_entity_name = True


class EnergiserSensor(_Base, SensorEntity):
    entity_description: EnergiserSensorDescription

    def __init__(self, coordinator: GallagherCoordinator, en_id: int, desc: EnergiserSensorDescription) -> None:
        super().__init__(coordinator)
        self._en_id = en_id
        self.entity_description = desc
        en = coordinator.data.energisers[en_id]
        self._attr_unique_id = f"{en_id}_{desc.key}"
        self._attr_device_info = energiser_device(en, coordinator.farm_id)

    @property
    def _en(self) -> Energiser | None:
        return self.coordinator.data.energisers.get(self._en_id)

    @property
    def available(self) -> bool:
        return super().available and self._en is not None

    @property
    def native_value(self) -> Any:
        en = self._en
        return self.entity_description.value_fn(en) if en else None


class ZoneSensor(_Base, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: GallagherCoordinator, en_id: int, zone_id: int, kind: str) -> None:
        super().__init__(coordinator)
        self._en_id = en_id
        self._zone_id = zone_id
        self._kind = kind
        en = coordinator.data.energisers[en_id]
        z = en.zones[zone_id]
        self._attr_unique_id = f"{zone_id}_{kind}"
        self._attr_device_info = energiser_device(en, coordinator.farm_id)
        self._attr_name = f"{zone_label(z)} {kind}"
        if kind == "voltage":
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.KILOVOLT
            self._attr_suggested_display_precision = 1
            self._attr_icon = "mdi:earth" if z.kind == "Earth" else "mdi:fence-electric"
        else:
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
            self._attr_suggested_display_precision = 0

    @property
    def _zone(self) -> Zone | None:
        en = self.coordinator.data.energisers.get(self._en_id)
        return en.zones.get(self._zone_id) if en else None

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def native_value(self) -> float | None:
        z = self._zone
        if not z:
            return None
        return z.reading.voltage if self._kind == "voltage" else z.reading.current

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        z = self._zone
        if not z or self._kind != "voltage":
            return None
        return {
            "zone_number": z.number,
            "status": z.status,
            "monitor_battery": z.battery,
            "last_reading": z.reading.timestamp.isoformat() if z.reading.timestamp else None,
            "monitor_last_seen": z.last_seen.isoformat() if z.last_seen else None,
        }


class AlertsSensor(_Base, SensorEntity):
    _attr_name = "Active alerts"
    _attr_icon = "mdi:alert"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: GallagherCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"farm_{coordinator.farm_id}_active_alerts"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"farm_{coordinator.farm_id}")},
            name="Gallagher Fence",
            manufacturer="Gallagher",
            model="Cloud account (read-only)",
        )

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.alerts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        alerts = []
        for a in self.coordinator.data.alerts[:20]:
            alerts.append(
                {
                    k: a.get(k)
                    for k in ("name", "description", "message", "alertType", "deviceName", "createdDate", "triggeredDate", "severity")
                    if a.get(k) is not None
                }
                or {"raw": str(a)[:200]}
            )
        return {"alerts": alerts}
