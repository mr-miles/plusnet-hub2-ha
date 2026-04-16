"""Shared fixtures for Plusnet Hub 2 integration tests."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

# ---------------------------------------------------------------------------
# Sample hub responses — realistic JavaScript variable declarations
# ---------------------------------------------------------------------------

MOCK_DEVICE_LIST_RESPONSE = """\
// BT Smart Hub 2 - Device List
var known_device_list=[
  {"mac":"aa:bb:cc:dd:ee:01","hostname":"my-laptop","ip":"192.168.1.50","Active":"1"},
  {"mac":"aa:bb:cc:dd:ee:02","hostname":"iphone","ip":"192.168.1.51","Active":"1"},
  {"mac":"aa:bb:cc:dd:ee:03","hostname":"smart-tv","ip":"192.168.1.52","Active":"0"},
  {"mac":"00:00:00:00:00:00","hostname":"","ip":"","Active":"0"}
];
"""

MOCK_DEVICE_LIST_EMPTY = """\
var known_device_list=[];
"""

MOCK_OWL_RESPONSE = """\
var owl_station=[
  {"mac":"aa:bb:cc:dd:ee:01","ConnectionType":"Ethernet"},
  {"mac":"aa:bb:cc:dd:ee:02","ConnectionType":"5GHz"},
  {"mac":"aa:bb:cc:dd:ee:03","ConnectionType":"2.4GHz"}
];
var owl_tplg=[
  {"mac":"aa:bb:cc:dd:ee:ff","type":"hub"}
];
"""

MOCK_DEVICE_LIST_SINGLE_QUOTES = """\
var known_device_list=[
  {'mac':'bb:cc:dd:ee:ff:01','hostname':'desktop','ip':'192.168.1.60','Active':'1'}
];
"""

# What _parse_devices / coordinator returns for the mock device list
EXPECTED_DEVICES = {
    "AA:BB:CC:DD:EE:01": {
        "mac": "AA:BB:CC:DD:EE:01",
        "hostname": "my-laptop",
        "ip": "192.168.1.50",
        "connected": True,
        "connection_type": "Ethernet",
    },
    "AA:BB:CC:DD:EE:02": {
        "mac": "AA:BB:CC:DD:EE:02",
        "hostname": "iphone",
        "ip": "192.168.1.51",
        "connected": True,
        "connection_type": "5GHz",
    },
    "AA:BB:CC:DD:EE:03": {
        "mac": "AA:BB:CC:DD:EE:03",
        "hostname": "smart-tv",
        "ip": "192.168.1.52",
        "connected": False,
        "connection_type": "2.4GHz",
    },
}


# ---------------------------------------------------------------------------
# Config entry data
# ---------------------------------------------------------------------------

MOCK_CONFIG_DATA = {
    "host": "192.168.1.254",
    "username": "admin",
    "password": "test-password",
    "scan_interval": 30,
}


# ---------------------------------------------------------------------------
# Coordinator patch helper
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_coordinator_data() -> dict:
    """Return a copy of the expected devices dict for patching."""
    return dict(EXPECTED_DEVICES)


@pytest.fixture
def mock_successful_fetch() -> Generator:
    """Patch the coordinator's _async_fetch_devices to return mock data."""
    with patch(
        "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator._async_fetch_devices",
        new_callable=AsyncMock,
        return_value=dict(EXPECTED_DEVICES),
    ) as mock:
        yield mock


@pytest.fixture
def mock_config_entry(hass: HomeAssistant):
    """Create and return a mock config entry."""
    from homeassistant.config_entries import ConfigEntry

    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = MOCK_CONFIG_DATA
    entry.options = {}
    entry.domain = "plusnet_hub2"
    entry.title = "Plusnet Hub 2 (192.168.1.254)"
    return entry
