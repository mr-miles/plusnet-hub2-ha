"""Tests for the Plusnet Hub 2 coordinator — parsing and HTTP logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.plusnet_hub2.coordinator import (
    PlusnetHub2AuthError,
    PlusnetHub2ConnectionError,
    PlusnetHub2Coordinator,
    _extract_js_variable,
    _parse_devices,
)

from .conftest import (
    MOCK_DEVICE_LIST_APOSTROPHE,
    MOCK_DEVICE_LIST_EMPTY,
    MOCK_DEVICE_LIST_ENCODED_APOSTROPHE,
    MOCK_DEVICE_LIST_REAL_HUB_RESPONSE,
    MOCK_DEVICE_LIST_RESPONSE,
    MOCK_OWL_RESPONSE,
)


# ---------------------------------------------------------------------------
# Unit tests for _extract_js_variable
# ---------------------------------------------------------------------------


class TestExtractJsVariable:
    """Tests for the JavaScript variable parser."""

    def test_extracts_standard_device_list(self):
        result = _extract_js_variable(MOCK_DEVICE_LIST_RESPONSE, "known_device_list")
        assert isinstance(result, list)
        assert len(result) == 4  # includes the 00:00 entry

    def test_returns_empty_for_missing_variable(self):
        result = _extract_js_variable(MOCK_DEVICE_LIST_RESPONSE, "nonexistent_var")
        assert result == []

    def test_parses_hostname_with_apostrophe(self):
        result = _extract_js_variable(MOCK_DEVICE_LIST_APOSTROPHE, "known_device_list")
        assert len(result) == 2
        assert result[0]["hostname"] == "Tom's iPhone"
        assert result[1]["mac"] == "cc:dd:ee:ff:00:02"

    def test_parses_percent_encoded_apostrophe_in_field_value(self):
        """A %27 (percent-encoded apostrophe) inside a single-quoted JS value
        must not be decoded before parsing, or it would terminate the JS
        string early and break the surrounding structure.
        """
        result = _extract_js_variable(MOCK_DEVICE_LIST_ENCODED_APOSTROPHE, "known_device_list")
        assert len(result) == 1
        assert result[0]["hostname"] == "O'Brien-iPhone"
        assert result[0]["mac"] == "AA:BB:CC:11:22:04"
        assert result[0]["ip"] == "192.168.1.13"

    def test_parses_real_hub_response(self):
        """Regression test modelled on an actual captured /cgi/cgi_basicMyDevice.js response.

        Real firmware emits unquoted keys, single-quoted values, and
        percent-encodes punctuation in every field — plus a trailing `null`
        entry and other var/addCfg(...) declarations following in the same
        body that must not be swept in.
        """
        result = _extract_js_variable(MOCK_DEVICE_LIST_REAL_HUB_RESPONSE, "known_device_list")
        assert len(result) == 4  # 3 devices + trailing null
        assert result[0]["mac"] == "AA:BB:CC:11:22:01"
        assert result[0]["hostname"] == "TestPhone"
        assert result[0]["ip"] == "192.168.1.10"
        assert result[1]["hostname"] == "Smart-Speaker"
        assert result[2]["hostname"] == ""
        assert result[3] is None

        devices = _parse_devices(result)
        assert len(devices) == 3  # None entry filtered out
        assert devices["AA:BB:CC:11:22:01"]["hostname"] == "TestPhone"
        # hostname is blank, so it falls back to the hub's own "name" placeholder
        assert devices["AA:BB:CC:11:22:03"]["hostname"] == "unknown_AA:BB:CC:11:22:03"
        # activity:'0'/'1' is the real hub's connected-status field
        assert devices["AA:BB:CC:11:22:01"]["connected"] is False  # activity:'0'
        assert devices["AA:BB:CC:11:22:02"]["connected"] is True  # activity:'1'
        assert devices["AA:BB:CC:11:22:03"]["connected"] is False  # activity:'0'

    def test_returns_empty_list_on_malformed_js(self):
        """Unparseable content (even after extraction) must not raise — just log and return []."""
        body = "var known_device_list=[{mac:'AA:BB:CC:11:22:01',,,}];"
        result = _extract_js_variable(body, "known_device_list")
        assert result == []

    def test_decodes_nested_list_of_lists(self):
        """Some hub vars (e.g. dhcp_log) are arrays of arrays of strings, not
        arrays of objects — URL-decoding must recurse into those too.
        """
        body = (
            "var dhcp_log=[['192%2E168%2E1%2E242','0C%3A7E%3A24%3A22%3A02%3A42',"
            "'garmin%2Dfenix8'],\nnull];"
        )
        result = _extract_js_variable(body, "dhcp_log")
        assert result == [["192.168.1.242", "0C:7E:24:22:02:42", "garmin-fenix8"], None]

    def test_object_keys_are_not_url_decoded(self):
        """Only field *values* are URL-decoded — object keys must be left
        untouched even if quoted and percent-encoded-looking.
        """
        body = "var known_device_list=[{'weird%2Dkey':'AA%3ABB%3ACC%3A11%3A22%3A01'}];"
        result = _extract_js_variable(body, "known_device_list")
        assert result[0] == {"weird%2Dkey": "AA:BB:CC:11:22:01"}

    def test_parses_empty_list(self):
        result = _extract_js_variable(MOCK_DEVICE_LIST_EMPTY, "known_device_list")
        assert result == []

    def test_parses_owl_station(self):
        result = _extract_js_variable(MOCK_OWL_RESPONSE, "owl_station")
        assert len(result) == 3
        assert result[0]["ConnectionType"] == "Ethernet"

    def test_parses_owl_tplg(self):
        result = _extract_js_variable(MOCK_OWL_RESPONSE, "owl_tplg")
        assert len(result) == 1
        assert result[0]["type"] == "hub"

    def test_url_decodes_content(self):
        body = "var known_device_list=[{\"mac\":\"aa:bb:cc:dd:ee:01\",\"hostname\":\"my%20laptop\",\"ip\":\"192.168.1.1\",\"Active\":\"1\"}];"
        result = _extract_js_variable(body, "known_device_list")
        assert result[0]["hostname"] == "my laptop"

    def test_html_entity_decodes_content(self):
        """Hub may HTML-encode its CGI response (e.g. after certain firmware updates).

        The raw response looks like:
          known_device_list=[{&quot;mac&quot;:&quot;aa:bb:cc:dd:ee:01&quot;,...}];
        Without html.unescape() this raises JSONDecodeError: Expecting ',' delimiter.
        """
        body = (
            "known_device_list=[{&quot;mac&quot;:&quot;aa:bb:cc:dd:ee:01&quot;,"
            "&quot;hostname&quot;:&quot;iphone&quot;,"
            "&quot;ip&quot;:&quot;192.168.1.5&quot;,"
            "&quot;Active&quot;:&quot;1&quot;}];"
        )
        result = _extract_js_variable(body, "known_device_list")
        assert len(result) == 1
        assert result[0]["mac"] == "aa:bb:cc:dd:ee:01"
        assert result[0]["hostname"] == "iphone"


# ---------------------------------------------------------------------------
# Unit tests for _parse_devices
# ---------------------------------------------------------------------------


class TestParseDevices:
    """Tests for device list normalisation."""

    def test_filters_zero_mac(self):
        raw = [
            {"mac": "00:00:00:00:00:00", "hostname": "junk", "ip": "", "Active": "0"},
            {"mac": "aa:bb:cc:dd:ee:01", "hostname": "laptop", "ip": "192.168.1.10", "Active": "1"},
        ]
        result = _parse_devices(raw)
        assert "00:00:00:00:00:00" not in result
        assert "AA:BB:CC:DD:EE:01" in result

    def test_normalises_mac_to_uppercase(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "1.2.3.4", "Active": "1"}]
        result = _parse_devices(raw)
        assert "AA:BB:CC:DD:EE:01" in result

    def test_active_string_1_is_connected(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "Active": "1"}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is True

    def test_active_string_0_is_not_connected(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "Active": "0"}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is False

    def test_active_bool_true(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "Active": True}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is True

    def test_active_bool_false(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "Active": False}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is False

    def test_activity_field_1_is_connected(self):
        """Real BT Smart Hub 2 / Plusnet Hub 2 responses use "activity", not
        "Active"/"active" — see MOCK_DEVICE_LIST_REAL_HUB_RESPONSE.
        """
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "activity": "1"}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is True

    def test_activity_field_0_is_not_connected(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "activity": "0"}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is False

    def test_active_key_takes_precedence_over_activity(self):
        """If both keys are somehow present, the explicit "Active" wins."""
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "Active": "1", "activity": "0"}]
        assert _parse_devices(raw)["AA:BB:CC:DD:EE:01"]["connected"] is True

    def test_filters_none_entries(self):
        """Arrays commonly end with a trailing `null` sentinel entry (see
        commit 67538e8) — non-dict entries must be skipped, not raise.
        """
        raw = [None, {"mac": "aa:bb:cc:dd:ee:01", "hostname": "x", "ip": "", "Active": "1"}, None]
        result = _parse_devices(raw)
        assert len(result) == 1
        assert "AA:BB:CC:DD:EE:01" in result

    def test_falls_back_to_mac_for_empty_hostname(self):
        raw = [{"mac": "aa:bb:cc:dd:ee:01", "hostname": "", "ip": "", "Active": "1"}]
        result = _parse_devices(raw)
        assert result["AA:BB:CC:DD:EE:01"]["hostname"] == "AA:BB:CC:DD:EE:01"

    def test_handles_physaddress_key(self):
        raw = [{"PhysAddress": "aa:bb:cc:dd:ee:02", "UserHostName": "server", "IPAddress": "10.0.0.1", "Active": "1"}]
        result = _parse_devices(raw)
        assert "AA:BB:CC:DD:EE:02" in result

    def test_empty_list(self):
        assert _parse_devices([]) == {}


# ---------------------------------------------------------------------------
# Integration tests for PlusnetHub2Coordinator
# ---------------------------------------------------------------------------


class TestPlusnetHub2Coordinator:
    """Tests for the full coordinator fetch cycle."""

    def _make_coordinator(self, hass, host="192.168.1.254", password="secret"):
        import types

        fake_entry = types.SimpleNamespace(
            data={
                "host": host,
                "username": "admin",
                "password": password,
                "scan_interval": 30,
            },
            options={},
        )
        return PlusnetHub2Coordinator(hass, fake_entry)

    @pytest.mark.asyncio
    async def test_fetch_returns_parsed_devices(self, hass):
        """Coordinator returns properly parsed device dict."""
        coordinator = self._make_coordinator(hass)

        mock_response_device = MagicMock()
        mock_response_device.__aenter__ = AsyncMock(return_value=mock_response_device)
        mock_response_device.__aexit__ = AsyncMock(return_value=False)
        mock_response_device.status = 200
        mock_response_device.text = AsyncMock(return_value=MOCK_DEVICE_LIST_RESPONSE)
        mock_response_device.raise_for_status = MagicMock()

        mock_response_owl = MagicMock()
        mock_response_owl.__aenter__ = AsyncMock(return_value=mock_response_owl)
        mock_response_owl.__aexit__ = AsyncMock(return_value=False)
        mock_response_owl.status = 200
        mock_response_owl.text = AsyncMock(return_value=MOCK_OWL_RESPONSE)
        mock_response_owl.raise_for_status = MagicMock()

        with patch("aiohttp.ClientSession") as mock_session_cls:
            session_instance = MagicMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=False)

            def get_side_effect(url, **kwargs):
                if "cgi_basicMyDevice" in url:
                    return mock_response_device
                return mock_response_owl

            session_instance.get = MagicMock(side_effect=get_side_effect)
            mock_session_cls.return_value = session_instance

            # Patch TCPConnector too
            with patch("aiohttp.TCPConnector"):
                result = await coordinator._async_fetch_devices()

        assert "AA:BB:CC:DD:EE:01" in result
        assert result["AA:BB:CC:DD:EE:01"]["hostname"] == "my-laptop"
        assert result["AA:BB:CC:DD:EE:01"]["connected"] is True
        assert "AA:BB:CC:DD:EE:03" in result
        assert result["AA:BB:CC:DD:EE:03"]["connected"] is False
        # Zero MAC should be filtered
        assert "00:00:00:00:00:00" not in result

    @pytest.mark.asyncio
    async def test_fetch_raises_auth_error_on_401(self, hass):
        coordinator = self._make_coordinator(hass)

        mock_response = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_response.status = 401
        mock_response.raise_for_status = MagicMock()

        with patch("aiohttp.ClientSession") as mock_session_cls:
            session_instance = MagicMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=False)
            session_instance.get = MagicMock(return_value=mock_response)
            mock_session_cls.return_value = session_instance

            with patch("aiohttp.TCPConnector"):
                with pytest.raises(PlusnetHub2AuthError):
                    await coordinator._async_fetch_devices()

    @pytest.mark.asyncio
    async def test_fetch_raises_auth_error_on_403(self, hass):
        coordinator = self._make_coordinator(hass)

        mock_response = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_response.status = 403
        mock_response.raise_for_status = MagicMock()

        with patch("aiohttp.ClientSession") as mock_session_cls:
            session_instance = MagicMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=False)
            session_instance.get = MagicMock(return_value=mock_response)
            mock_session_cls.return_value = session_instance

            with patch("aiohttp.TCPConnector"):
                with pytest.raises(PlusnetHub2AuthError):
                    await coordinator._async_fetch_devices()

    @pytest.mark.asyncio
    async def test_fetch_raises_connection_error_on_timeout(self, hass):
        import asyncio

        coordinator = self._make_coordinator(hass)

        with patch("aiohttp.ClientSession") as mock_session_cls:
            session_instance = MagicMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=False)
            session_instance.get.side_effect = TimeoutError("timed out")
            mock_session_cls.return_value = session_instance

            with patch("aiohttp.TCPConnector"):
                with pytest.raises(PlusnetHub2ConnectionError):
                    await coordinator._async_fetch_devices()

    @pytest.mark.asyncio
    async def test_topology_failure_does_not_break_device_list(self, hass):
        """If cgi_owl.js fails, we still return the device list."""
        coordinator = self._make_coordinator(hass)

        mock_response_device = MagicMock()
        mock_response_device.__aenter__ = AsyncMock(return_value=mock_response_device)
        mock_response_device.__aexit__ = AsyncMock(return_value=False)
        mock_response_device.status = 200
        mock_response_device.text = AsyncMock(return_value=MOCK_DEVICE_LIST_RESPONSE)
        mock_response_device.raise_for_status = MagicMock()

        mock_response_owl = MagicMock()
        mock_response_owl.__aenter__ = AsyncMock(return_value=mock_response_owl)
        mock_response_owl.__aexit__ = AsyncMock(return_value=False)
        mock_response_owl.status = 404
        mock_response_owl.raise_for_status = MagicMock(
            side_effect=Exception("404 not found")
        )

        with patch("aiohttp.ClientSession") as mock_session_cls:
            session_instance = MagicMock()
            session_instance.__aenter__ = AsyncMock(return_value=session_instance)
            session_instance.__aexit__ = AsyncMock(return_value=False)

            def get_side_effect(url, **kwargs):
                if "cgi_basicMyDevice" in url:
                    return mock_response_device
                return mock_response_owl

            session_instance.get = MagicMock(side_effect=get_side_effect)
            mock_session_cls.return_value = session_instance

            with patch("aiohttp.TCPConnector"):
                result = await coordinator._async_fetch_devices()

        # Device list is still populated even though topology failed
        assert "AA:BB:CC:DD:EE:01" in result
