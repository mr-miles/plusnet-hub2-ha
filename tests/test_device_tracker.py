"""Tests for the Plusnet Hub 2 device tracker entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.device_tracker import SourceType
from homeassistant.core import HomeAssistant

from custom_components.plusnet_hub2.coordinator import PlusnetHub2Coordinator
from custom_components.plusnet_hub2.device_tracker import PlusnetHub2DeviceTracker

from .conftest import EXPECTED_DEVICES, MOCK_CONFIG_DATA


def _make_fake_entry(data=None, options=None):
    """Create a minimal fake ConfigEntry."""
    import types

    return types.SimpleNamespace(
        entry_id="test_entry_id",
        data=data or MOCK_CONFIG_DATA,
        options=options or {},
        domain="plusnet_hub2",
        title="Plusnet Hub 2 (192.168.1.254)",
    )


def _make_coordinator(hass, data=None):
    """Create a coordinator with pre-loaded data."""
    fake_entry = _make_fake_entry()
    coordinator = PlusnetHub2Coordinator(hass, fake_entry)
    coordinator.data = data or dict(EXPECTED_DEVICES)
    return coordinator


class TestPlusnetHub2DeviceTracker:
    """Tests for the ScannerEntity implementation."""

    def _make_tracker(self, hass, mac="AA:BB:CC:DD:EE:01", coordinator_data=None):
        coordinator = _make_coordinator(hass, data=coordinator_data)
        fake_entry = _make_fake_entry()
        initial_data = (coordinator_data or EXPECTED_DEVICES).get(mac, {})
        return PlusnetHub2DeviceTracker(coordinator, fake_entry, mac, initial_data)

    def test_is_connected_returns_true_for_active_device(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        assert tracker.is_connected is True

    def test_is_connected_returns_false_for_inactive_device(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:03")
        assert tracker.is_connected is False

    def test_source_type_is_router(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass)
        assert tracker.source_type == SourceType.ROUTER

    def test_ip_address_returns_device_ip(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        assert tracker.ip_address == "192.168.1.50"

    def test_ip_address_returns_none_when_empty(self, hass: HomeAssistant):
        data = {"AA:BB:CC:DD:EE:99": {"mac": "AA:BB:CC:DD:EE:99", "hostname": "x", "ip": "", "connected": True}}
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:99", coordinator_data=data)
        assert tracker.ip_address is None

    def test_mac_address_is_correct(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:02")
        assert tracker.mac_address == "AA:BB:CC:DD:EE:02"

    def test_hostname_returns_name(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        assert tracker.hostname == "my-laptop"

    def test_name_uses_hostname(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        assert tracker.name == "my-laptop"

    def test_name_falls_back_to_mac(self, hass: HomeAssistant):
        data = {
            "AA:BB:CC:DD:EE:99": {
                "mac": "AA:BB:CC:DD:EE:99",
                "hostname": "AA:BB:CC:DD:EE:99",
                "ip": "",
                "connected": True,
            }
        }
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:99", coordinator_data=data)
        assert tracker.name == "AA:BB:CC:DD:EE:99"

    def test_unique_id_format(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        assert tracker.unique_id == "plusnet_hub2_aa_bb_cc_dd_ee_01"

    def test_extra_state_attributes_includes_connection_type(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        attrs = tracker.extra_state_attributes
        assert attrs.get("connection_type") == "Ethernet"

    def test_extra_state_attributes_empty_when_no_connection_type(self, hass: HomeAssistant):
        data = {
            "AA:BB:CC:DD:EE:01": {
                "mac": "AA:BB:CC:DD:EE:01",
                "hostname": "my-laptop",
                "ip": "192.168.1.50",
                "connected": True,
                # No connection_type key
            }
        }
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01", coordinator_data=data)
        assert tracker.extra_state_attributes == {}

    def test_device_info_contains_hub_identifier(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass)
        info = tracker.device_info
        assert ("plusnet_hub2", "192.168.1.254") in info["identifiers"]

    def test_device_info_manufacturer(self, hass: HomeAssistant):
        tracker = self._make_tracker(hass)
        assert "Plusnet" in tracker.device_info["manufacturer"]

    def test_is_connected_false_when_device_absent_from_coordinator(self, hass: HomeAssistant):
        """If device disappears from coordinator data, entity should show disconnected."""
        tracker = self._make_tracker(hass, mac="AA:BB:CC:DD:EE:01")
        # Simulate device disappearing from coordinator data
        tracker.coordinator.data = {}
        assert tracker.is_connected is False
