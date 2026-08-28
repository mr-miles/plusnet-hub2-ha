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

# Regression fixture: a device name containing an apostrophe embedded in
# otherwise-valid double-quoted JSON (e.g. "Tom's iPhone"). This must not be
# mistaken for a single-quoted JSON string delimiter.
MOCK_DEVICE_LIST_APOSTROPHE = """\
var known_device_list=[
  {"mac":"cc:dd:ee:ff:00:01","hostname":"Tom's iPhone","ip":"192.168.1.70","Active":"1"},
  {"mac":"cc:dd:ee:ff:00:02","hostname":"other-device","ip":"192.168.1.71","Active":"1"}
];
"""

# Regression fixture: a hostname containing a *percent-encoded* apostrophe
# (%27) inside a single-quoted JS field value — the encoded form the hub
# would actually send. Decoding the raw text before parsing (rather than
# after) would turn %27 into a literal ' and terminate the JS string early,
# reintroducing the same class of bug the double-quoted apostrophe fixture
# above guards against.
MOCK_DEVICE_LIST_ENCODED_APOSTROPHE = """\
var known_device_list=[{mac:'AA%3ABB%3ACC%3A11%3A22%3A04',hostname:'O%27Brien%2DiPhone',ip:'192%2E168%2E1%2E13'}];
"""

# A structurally-faithful but anonymised excerpt modelled on an actual
# /cgi/cgi_basicMyDevice.js response. Real hub firmware emits unquoted
# object keys, single-quoted string values, and percent-encodes punctuation
# in every field (mac, ip, hostname, dates, ...). The array is terminated by
# a trailing `null` entry before `];`, and is immediately followed by other
# unrelated `var`/`addCfg(...)` declarations in the same response body — the
# extractor must stop at the first `];` and ignore everything after.
# MAC addresses, IPs, hostnames and timestamps below are synthetic.
MOCK_DEVICE_LIST_REAL_HUB_RESPONSE = """\
var known_device_list=[{mac:'AA%3ABB%3ACC%3A11%3A22%3A01',hostname:'TestPhone',ip:'192%2E168%2E1%2E10',ipv6:'',name:'TestPhone',activity:'0',os:'iOS',device:'TestPhone',time_first_seen:'2026%2F01%2F01%2000%3A00%3A00',time_last_active:'2026%2F01%2F02%2000%3A00%3A00',port:'wl0',reconnected:'0'},
{mac:'AA%3ABB%3ACC%3A11%3A22%3A02',hostname:'Smart%2DSpeaker',ip:'192%2E168%2E1%2E11',ipv6:'',name:'Smart%2DSpeaker',activity:'1',os:'Android',device:'STB',time_first_seen:'2026%2F01%2F01%2001%3A00%3A00',time_last_active:'2026%2F01%2F03%2000%3A00%3A00',port:'eth0',reconnected:'0'},
{mac:'AA%3ABB%3ACC%3A11%3A22%3A03',hostname:'',ip:'192%2E168%2E1%2E12',ipv6:'',name:'unknown%5FAA%3ABB%3ACC%3A11%3A22%3A03',activity:'0',os:'Unknown',device:'Unknown',time_first_seen:'2026%2F01%2F01%2002%3A00%3A00',time_last_active:'2026%2F01%2F04%2000%3A00%3A00',port:'eth0',reconnected:'0'},
null];
var rate = [{timestamp:'0',app:'4294967295',mac:'00%3A00%3A00%3A00%3A00%3A00',tx:'656',rx:'0'},
null];
addCfg("dhcpreserve1",68681729,'192%2E168%2E1%2E250%2C00%3A24%3A9B%3A5B%3A5F%3AD1%2C');
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
