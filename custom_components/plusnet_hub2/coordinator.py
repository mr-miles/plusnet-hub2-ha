"""DataUpdateCoordinator for the Plusnet Hub 2 / BT Smart Hub 2 integration.

This module handles all HTTP communication with the hub, parsing the JavaScript
variable declarations returned by its CGI endpoints, and managing re-authentication.

The BT Smart Hub 2 / Plusnet Hub 2 exposes connected device information via two
unauthenticated-but-Referer-gated JavaScript endpoints:
  - /cgi/cgi_basicMyDevice.js  →  known_device_list = [ ... ];
  - /cgi/cgi_owl.js            →  owl_station = [ ... ];  owl_tplg = [ ... ];

After firmware update V35 (~mid-2022) requests without a Referer header return HTTP 403.
This coordinator always sends the required Referer header.
"""

from __future__ import annotations

import html
import json
import logging
import re
import urllib.parse
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENDPOINT_DEVICE_LIST,
    ENDPOINT_TOPOLOGY,
    JS_VAR_DEVICE_LIST,
    JS_VAR_OWL_STATION,
    REFERER_PAGE,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class PlusnetHub2CoordinatorError(Exception):
    """Base error for coordinator failures."""


class PlusnetHub2AuthError(PlusnetHub2CoordinatorError):
    """Authentication failure."""


class PlusnetHub2ConnectionError(PlusnetHub2CoordinatorError):
    """Connection failure (hub unreachable, timeout)."""


def _build_referer(host: str) -> str:
    return f"http://{host}{REFERER_PAGE}"


def _extract_js_variable(body: str, var_name: str) -> list[dict]:
    """Extract a JavaScript variable assignment and convert to a Python list.

    The hub returns responses like:
        known_device_list=[{"mac":"aa:bb:cc:dd:ee:ff","ip":"192.168.1.10",...}];

    We need to:
    1. Locate the variable assignment
    2. Extract the JSON array between '=[' and '];'
    3. Fix JavaScript-isms (unquoted keys, single quotes, url-encoded chars)
    4. Parse as JSON
    """
    # Look for   varname = [ ... ];   (with optional whitespace)
    pattern = re.compile(
        r"\b" + re.escape(var_name) + r"\s*=\s*(\[.*?\]);",
        re.DOTALL,
    )
    match = pattern.search(body)
    if not match:
        _LOGGER.debug("Variable '%s' not found in response body", var_name)
        return []

    raw = match.group(1)

    # HTML-decode entities the hub occasionally embeds in its CGI responses
    # (e.g. &quot; → ", &amp; → &).  Without this step json.loads() raises
    # "Expecting ',' delimiter" because it sees literal &quot; instead of ".
    raw = html.unescape(raw)

    # URL-decode percent-encoded characters (e.g. %2E → .)
    raw = urllib.parse.unquote(raw)

    # The hub sometimes uses single-quoted strings; convert to double quotes.
    # First protect already-double-quoted content, then swap singles.
    # Simple approach: replace ' with " when used as JSON string delimiters.
    # We do a targeted replacement: single-quoted values → double-quoted.
    raw = re.sub(r"'([^']*)'", r'"\1"', raw)

    # Quote any bare (unquoted) object keys: { key: → { "key":
    raw = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', raw)

    # Replace JavaScript booleans/null if they snuck in unquoted  (true/false/null already valid JSON)
    # Replace '0' / '1' string-encoded booleans that the hub sometimes uses:
    # These show up as "Active":"1" / "Active":"0" — keep as strings, we parse them ourselves.

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _LOGGER.warning(
            "Failed to parse JS variable '%s' as JSON: %s\nRaw snippet: %.200s",
            var_name,
            exc,
            raw,
        )
        return []


def _parse_devices(raw_list: list[dict]) -> dict[str, dict[str, Any]]:
    """Convert the raw device list from the hub into a normalised dict keyed by MAC.

    Normalised device dict shape::

        {
            "mac": "AA:BB:CC:DD:EE:FF",
            "hostname": "my-laptop",
            "ip": "192.168.1.50",
            "connected": True,
        }
    """
    devices: dict[str, dict[str, Any]] = {}

    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        # The hub uses various key names across firmware versions
        mac = (
            entry.get("mac")
            or entry.get("PhysAddress")
            or entry.get("MACAddress")
            or ""
        ).upper().strip()

        if not mac or mac == "00:00:00:00:00:00":
            continue

        hostname = (
            entry.get("hostname")
            or entry.get("UserHostName")
            or entry.get("name")
            or ""
        ).strip() or mac

        ip = (
            entry.get("ip")
            or entry.get("IPAddress")
            or entry.get("ipv4")
            or ""
        ).strip()

        # "Active" may be "1"/"0", 1/0, True/False, or "true"/"false"
        active_raw = entry.get("Active", entry.get("active", entry.get("connected", "1")))
        if isinstance(active_raw, bool):
            connected = active_raw
        elif isinstance(active_raw, int):
            connected = bool(active_raw)
        else:
            connected = str(active_raw).lower() not in ("0", "false", "no", "")

        devices[mac] = {
            "mac": mac,
            "hostname": hostname,
            "ip": ip,
            "connected": connected,
        }

    return devices


class PlusnetHub2Coordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Coordinator that polls the Plusnet Hub 2 / BT Smart Hub 2 for connected devices.

    Data shape returned by ``async_refresh()``::

        {
            "AA:BB:CC:DD:EE:FF": {
                "mac": "AA:BB:CC:DD:EE:FF",
                "hostname": "my-laptop",
                "ip": "192.168.1.50",
                "connected": True,
            },
            ...
        }
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self.host: str = entry.data[CONF_HOST]
        self.username: str = entry.data.get(CONF_USERNAME, "")
        self.password: str = entry.data.get(CONF_PASSWORD, "")
        scan_interval: int = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _make_headers(self) -> dict[str, str]:
        """Build the request headers required by the hub."""
        return {
            "Referer": _build_referer(self.host),
            "User-Agent": (
                "Mozilla/5.0 (compatible; HomeAssistant PlusnetHub2)"
            ),
        }

    async def _fetch(self, session: aiohttp.ClientSession, path: str) -> str:
        """Fetch a single CGI endpoint and return the response body."""
        url = f"http://{self.host}{path}"
        headers = self._make_headers()

        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                allow_redirects=True,
            ) as resp:
                if resp.status == 401:
                    raise PlusnetHub2AuthError(
                        f"Hub returned 401 for {url}. "
                        "Check your credentials in the integration options."
                    )
                if resp.status == 403:
                    raise PlusnetHub2AuthError(
                        f"Hub returned 403 for {url}. "
                        "The hub may require authentication or its firmware "
                        "changed the Referer requirement."
                    )
                resp.raise_for_status()
                return await resp.text()
        except aiohttp.ClientConnectionError as exc:
            raise PlusnetHub2ConnectionError(
                f"Cannot connect to hub at {self.host}: {exc}"
            ) from exc
        except aiohttp.ClientResponseError as exc:
            raise PlusnetHub2ConnectionError(
                f"Hub at {self.host} returned HTTP {exc.status}"
            ) from exc
        except TimeoutError as exc:
            raise PlusnetHub2ConnectionError(
                f"Timeout connecting to hub at {self.host}"
            ) from exc

    # ------------------------------------------------------------------
    # Public async helpers (used by config_flow for validation)
    # ------------------------------------------------------------------

    async def async_validate_connection(self) -> dict[str, dict[str, Any]]:
        """Attempt to fetch device list; raise on failure.

        Called during config flow to validate host/credentials.
        Returns device dict on success.
        """
        return await self._async_fetch_devices()

    # ------------------------------------------------------------------
    # DataUpdateCoordinator implementation
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from hub — called by DataUpdateCoordinator."""
        try:
            return await self._async_fetch_devices()
        except PlusnetHub2AuthError as exc:
            # Auth failures are permanent until user reconfigures
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except PlusnetHub2ConnectionError as exc:
            raise UpdateFailed(str(exc)) from exc

    async def _async_fetch_devices(self) -> dict[str, dict[str, Any]]:
        """Perform actual HTTP fetch and parse device list."""
        connector = aiohttp.TCPConnector(limit=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Always fetch the primary device list
            device_body = await self._fetch(session, ENDPOINT_DEVICE_LIST)
            raw_devices = _extract_js_variable(device_body, JS_VAR_DEVICE_LIST)

            if not raw_devices:
                # The hub returned something but we couldn't parse it.
                # Try the alternative variable name used by some firmware versions.
                raw_devices = _extract_js_variable(device_body, "deviceList")

            # Optionally enrich with topology (connection type, parent device)
            # This is best-effort; failures here don't break device tracking.
            topology_map: dict[str, str] = {}
            try:
                topo_body = await self._fetch(session, ENDPOINT_TOPOLOGY)
                stations = _extract_js_variable(topo_body, JS_VAR_OWL_STATION)
                for station in stations:
                    if not isinstance(station, dict):
                        continue
                    mac = (station.get("mac") or station.get("PhysAddress") or "").upper()
                    conn_type = station.get("ConnectionType") or station.get("connectionType") or ""
                    if mac:
                        topology_map[mac] = conn_type
            except (PlusnetHub2ConnectionError, PlusnetHub2AuthError) as exc:
                _LOGGER.debug("Could not fetch topology data: %s", exc)

        devices = _parse_devices(raw_devices)

        # Merge connection type from topology
        for mac, info in devices.items():
            if mac in topology_map:
                info["connection_type"] = topology_map[mac]

        _LOGGER.debug(
            "Fetched %d devices from hub at %s (%d active)",
            len(devices),
            self.host,
            sum(1 for d in devices.values() if d["connected"]),
        )
        return devices
