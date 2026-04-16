"""Device tracker platform for Plusnet Hub 2 / BT Smart Hub 2.

Creates one ScannerEntity per MAC address seen by the hub.
Entities are added dynamically as new devices are discovered.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import (
    DOMAIN as DEVICE_TRACKER_DOMAIN,
    ScannerEntity,
    SourceType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, DOMAIN, MANUFACTURER
from .coordinator import PlusnetHub2Coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device trackers from a config entry."""
    coordinator: PlusnetHub2Coordinator = hass.data[DOMAIN][entry.entry_id]

    # Track which MACs we've already created entities for
    tracked_macs: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        """Add entities for any newly discovered MACs."""
        new_entities: list[PlusnetHub2DeviceTracker] = []
        for mac, device_data in coordinator.data.items():
            if mac not in tracked_macs:
                tracked_macs.add(mac)
                new_entities.append(
                    PlusnetHub2DeviceTracker(coordinator, entry, mac, device_data)
                )
        if new_entities:
            _LOGGER.debug("Adding %d new device tracker entities", len(new_entities))
            async_add_entities(new_entities)

    # Add entities for devices found on first poll
    _add_new_devices()

    # Subscribe to future coordinator updates to discover new devices
    coordinator.async_add_listener(_add_new_devices)


class PlusnetHub2DeviceTracker(
    CoordinatorEntity[PlusnetHub2Coordinator], ScannerEntity
):
    """Represents a single device tracked via the Plusnet Hub 2.

    Each instance corresponds to one MAC address observed on the hub's
    device list. The entity is marked "home" when the hub reports the
    device as active/connected.
    """

    _attr_source_type = SourceType.ROUTER
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PlusnetHub2Coordinator,
        entry: ConfigEntry,
        mac: str,
        initial_data: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._entry = entry

        # Unique ID is stable and based on MAC
        self._attr_unique_id = f"{DOMAIN}_{mac.lower().replace(':', '_')}"

        # Use hostname as the name; will update from coordinator data
        self._attr_name = initial_data.get("hostname") or mac

    # ------------------------------------------------------------------
    # ScannerEntity properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Return True when the hub reports this device as active."""
        device_data = self.coordinator.data.get(self._mac, {})
        return bool(device_data.get("connected", False))

    @property
    def ip_address(self) -> str | None:
        """Return the device's current IP address."""
        return self.coordinator.data.get(self._mac, {}).get("ip") or None

    @property
    def mac_address(self) -> str:
        """Return the device MAC address (used for entity registry lookup)."""
        return self._mac

    @property
    def hostname(self) -> str | None:
        """Return the device hostname."""
        device_data = self.coordinator.data.get(self._mac, {})
        return device_data.get("hostname") or None

    # ------------------------------------------------------------------
    # Entity metadata
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Use the hostname as entity name, falling back to MAC."""
        return self.hostname or self._mac

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes shown in the UI."""
        device_data = self.coordinator.data.get(self._mac, {})
        attrs: dict[str, Any] = {}
        if conn_type := device_data.get("connection_type"):
            attrs["connection_type"] = conn_type
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Link all tracker entities to the hub device entry."""
        host = self._entry.data[CONF_HOST]
        return DeviceInfo(
            identifiers={(DOMAIN, host)},
            name=f"Plusnet Hub 2 ({host})",
            manufacturer=MANUFACTURER,
            model="Plusnet Hub 2 / BT Smart Hub 2",
            configuration_url=f"http://{host}/",
        )
