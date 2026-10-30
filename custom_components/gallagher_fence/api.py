"""Minimal read-only client for the Gallagher Animal Management cloud API.

Only GET requests are made against device data.  Nothing in this module can
turn an energiser on or off, change alerts or alter any setting.
"""
from __future__ import annotations

import time
from typing import Any

import aiohttp

from .const import API_BASE, USER_AGENT

ENERGIZER_EXCLUDE = (
    "zones.systemAlertInstances,zones.deviceAlertInstances,"
    "systemAlertInstances,deviceAlertInstances"
)


class GallagherAuthError(Exception):
    """Credentials or refresh token rejected."""


class GallagherApiError(Exception):
    """Any other API or network failure."""


class GallagherApi:
    """Talks to am.app.gallagher.com the same way the Gallagher Devices app does."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self.refresh_token = refresh_token
        self._access_token: str | None = None
        self._access_expires = 0.0

    # ---------------------------------------------------------------- auth
    def _store_tokens(self, data: dict[str, Any]) -> None:
        token = data.get("access_token")
        if not token:
            raise GallagherAuthError("No access token in response")
        self._access_token = token
        self._access_expires = time.monotonic() + int(data.get("expires_in", 600)) - 60
        if data.get("refresh_token"):
            self.refresh_token = data["refresh_token"]

    async def _post_auth(self, url: str, data: Any) -> dict[str, Any]:
        headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
        try:
            async with self._session.post(
                url, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status in (400, 401, 403):
                    raise GallagherAuthError(f"Login rejected ({resp.status})")
                if resp.status != 200:
                    raise GallagherApiError(f"Login failed ({resp.status})")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise GallagherApiError(str(err)) from err

    async def login(self) -> None:
        """Log in with username and password (multipart form, as the app does)."""
        writer = aiohttp.MultipartWriter("form-data")
        for name, value in (("username", self._username), ("password", self._password)):
            part = writer.append(value)
            part.set_content_disposition("form-data", name=name)
        self._store_tokens(await self._post_auth(f"{API_BASE}/auth/login/offline", writer))

    async def _refresh(self) -> None:
        self._store_tokens(
            await self._post_auth(
                f"{API_BASE}/auth/login/refreshtoken/offline",
                {"refreshToken": self.refresh_token},
            )
        )

    async def ensure_token(self) -> None:
        if self._access_token and time.monotonic() < self._access_expires:
            return
        if self.refresh_token:
            try:
                await self._refresh()
                return
            except GallagherAuthError:
                self.refresh_token = None
        await self.login()

    # ----------------------------------------------------------------- GET
    async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        await self.ensure_token()
        for attempt in (1, 2):
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Authorization": f"Bearer {self._access_token}",
            }
            try:
                async with self._session.get(
                    f"{API_BASE}{path}",
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        self._access_token = None
                        await self.ensure_token()
                        continue
                    if resp.status in (401, 403):
                        raise GallagherAuthError(f"Access denied ({resp.status})")
                    if resp.status != 200:
                        raise GallagherApiError(f"GET {path} failed ({resp.status})")
                    return await resp.json(content_type=None)
            except aiohttp.ClientError as err:
                raise GallagherApiError(str(err)) from err
        raise GallagherApiError(f"GET {path} failed")

    async def farms(self) -> list[dict[str, Any]]:
        return (await self._get("/v2.0/farms")).get("values", [])

    async def energizers(self, farm_id: int) -> list[dict[str, Any]]:
        data = await self._get(
            f"/v2.0/farms/{farm_id}/energizers", {"exclude": ENERGIZER_EXCLUDE}
        )
        return data.get("values", [])

    async def gateways(self, farm_id: int) -> list[dict[str, Any]]:
        return (await self._get(f"/v2.0/farms/{farm_id}/gateways")).get("values", [])

    async def active_alerts(self, farm_id: int) -> list[dict[str, Any]]:
        data = await self._get(
            f"/v2.0/farms/{farm_id}/alerts/triggered", {"filter": "resolved eq false"}
        )
        return data.get("values", [])
