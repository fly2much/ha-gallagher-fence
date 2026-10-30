"""Polling coordinator and data model for Gallagher Fence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import GallagherApi, GallagherApiError, GallagherAuthError
from .const import (
    CONF_FARM_ID,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_MINUTES,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    STALE_ZONE_DAYS,
)

_LOGGER = logging.getLogger(__name__)


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(str(value))


@dataclass
class Reading:
    voltage: float | None = None  # kV
    current: float | None = None  # A
    timestamp: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, rec: dict[str, Any] | None) -> "Reading":
        if not rec:
            return cls()
        extra: dict[str, Any] = {}
        raw = rec.get("extra")
        if isinstance(raw, str) and raw:
            try:
                extra = json.loads(raw)
            except ValueError:
                extra = {}
        elif isinstance(raw, dict):
            extra = raw
        v = rec.get("voltage")
        a = rec.get("amperage")
        return cls(
            voltage=round(float(v), 1) if v is not None else None,
            current=round(float(a), 1) if a is not None else None,
            timestamp=_ts(rec.get("timestamp")),
            extra=extra,
        )


@dataclass
class Zone:
    device_id: int
    name: str
    kind: str  # "Zone" or "Earth"
    number: int | None
    status: str | None
    battery: str | None
    reading: Reading
    last_seen: datetime | None


@dataclass
class Energiser:
    device_id: int
    name: str
    model: str | None
    serial: str | None
    firmware: str | None
    status: str | None
    battery: str | None
    gateway_id: int | None
    reading: Reading
    last_seen: datetime | None
    zones: dict[int, Zone]


@dataclass
class Gateway:
    id: int
    device_id: str
    kind: str | None
    status: str | None
    firmware: str | None
    network: str | None
    last_online: datetime | None


@dataclass
class FenceData:
    energisers: dict[int, Energiser]
    gateways: dict[int, Gateway]
    alerts: list[dict[str, Any]]


def parse_energisers(values: list[dict[str, Any]]) -> dict[int, Energiser]:
    """Turn the /energizers payload into active energisers with live zones only."""
    out: dict[int, Energiser] = {}
    for en in values:
        if not en.get("isActive", True):
            continue  # e.g. a replaced gateway/energiser left on the account
        zones_raw = en.get("zones") or []
        readings = [Reading.from_api(z.get("latestRecord")) for z in zones_raw]
        newest = max((r.timestamp for r in readings if r.timestamp), default=None)
        zones: dict[int, Zone] = {}
        for z, rd in zip(zones_raw, readings):
            if newest and rd.timestamp and newest - rd.timestamp > timedelta(days=STALE_ZONE_DAYS):
                continue  # leftover entry from an old/replaced monitor
            if z.get("isActive") is False:
                continue
            zones[int(z["deviceID"])] = Zone(
                device_id=int(z["deviceID"]),
                name=z.get("name") or f"Zone {z.get('zoneNumber')}",
                kind=z.get("deviceType") or "Zone",
                number=z.get("zoneNumber"),
                status=z.get("status"),
                battery=z.get("batteryStatus"),
                reading=rd,
                last_seen=_ts(z.get("lastSeenDate")),
            )
        out[int(en["deviceID"])] = Energiser(
            device_id=int(en["deviceID"]),
            name=en.get("name") or en.get("model") or str(en["deviceID"]),
            model=en.get("model"),
            serial=en.get("serialNumber"),
            firmware=en.get("firmwareVersion"),
            status=en.get("status"),
            battery=en.get("batteryStatus"),
            gateway_id=en.get("gatewayID"),
            reading=Reading.from_api(en.get("latestRecord")),
            last_seen=_ts(en.get("lastSeenDate")),
            zones=zones,
        )
    return out


def parse_gateways(values: list[dict[str, Any]]) -> dict[int, Gateway]:
    return {
        int(g["id"]): Gateway(
            id=int(g["id"]),
            device_id=str(g.get("deviceID")),
            kind=g.get("gatewayType"),
            status=g.get("status"),
            firmware=g.get("firmwareVersion"),
            network=g.get("networkName") or None,
            last_online=_ts(g.get("lastOnlineDate")),
        )
        for g in values
        if g.get("enabled", True)
    }


type GallagherConfigEntry = ConfigEntry["GallagherCoordinator"]


class GallagherCoordinator(DataUpdateCoordinator[FenceData]):
    """Polls the Gallagher cloud every few minutes.  Read-only."""

    config_entry: GallagherConfigEntry

    def __init__(self, hass: HomeAssistant, entry: GallagherConfigEntry, api: GallagherApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=int(entry.options.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES))
            ),
        )
        self.api = api
        self.farm_id = int(entry.data[CONF_FARM_ID])

    async def _async_update_data(self) -> FenceData:
        try:
            energisers = await self.api.energizers(self.farm_id)
            gateways = await self.api.gateways(self.farm_id)
            try:
                alerts = await self.api.active_alerts(self.farm_id)
            except GallagherApiError:
                alerts = self.data.alerts if self.data else []
        except GallagherAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GallagherApiError as err:
            raise UpdateFailed(str(err)) from err

        # Keep the (possibly rotated) refresh token so restarts don't need the password.
        if self.api.refresh_token and self.api.refresh_token != self.config_entry.data.get(
            CONF_REFRESH_TOKEN
        ):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_REFRESH_TOKEN: self.api.refresh_token},
            )

        return FenceData(
            energisers=parse_energisers(energisers),
            gateways=parse_gateways(gateways),
            alerts=alerts,
        )
