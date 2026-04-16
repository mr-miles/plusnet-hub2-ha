"""Tests for the Plusnet Hub 2 config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.plusnet_hub2.coordinator import (
    PlusnetHub2AuthError,
    PlusnetHub2ConnectionError,
)

from .conftest import EXPECTED_DEVICES, MOCK_CONFIG_DATA

DOMAIN = "plusnet_hub2"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for tests."""
    yield


class TestConfigFlowUser:
    """Tests for the user config flow step."""

    @pytest.mark.asyncio
    async def test_shows_form_with_defaults(self, hass: HomeAssistant):
        """Config flow shows the form on initial invocation."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"
        assert not result["errors"]

    @pytest.mark.asyncio
    async def test_creates_entry_on_successful_connection(self, hass: HomeAssistant):
        """Config flow creates an entry when hub connection succeeds."""
        with patch(
            "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator.async_validate_connection",
            new_callable=AsyncMock,
            return_value=dict(EXPECTED_DEVICES),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=MOCK_CONFIG_DATA,
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Plusnet Hub 2 (192.168.1.254)"
        assert result["data"]["host"] == "192.168.1.254"
        assert result["data"]["password"] == "test-password"

    @pytest.mark.asyncio
    async def test_shows_error_on_auth_failure(self, hass: HomeAssistant):
        """Config flow shows invalid_auth error when credentials are wrong."""
        with patch(
            "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator.async_validate_connection",
            new_callable=AsyncMock,
            side_effect=PlusnetHub2AuthError("bad creds"),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=MOCK_CONFIG_DATA,
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "invalid_auth"

    @pytest.mark.asyncio
    async def test_shows_error_on_connection_failure(self, hass: HomeAssistant):
        """Config flow shows cannot_connect error when hub is unreachable."""
        with patch(
            "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator.async_validate_connection",
            new_callable=AsyncMock,
            side_effect=PlusnetHub2ConnectionError("timeout"),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=MOCK_CONFIG_DATA,
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "cannot_connect"

    @pytest.mark.asyncio
    async def test_aborts_if_already_configured(self, hass: HomeAssistant):
        """Config flow aborts if the same host is already configured."""
        # Create a first entry
        with patch(
            "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator.async_validate_connection",
            new_callable=AsyncMock,
            return_value=dict(EXPECTED_DEVICES),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=MOCK_CONFIG_DATA,
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Try to add the same host again
        with patch(
            "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator.async_validate_connection",
            new_callable=AsyncMock,
            return_value=dict(EXPECTED_DEVICES),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=MOCK_CONFIG_DATA,
            )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestOptionsFlow:
    """Tests for the options flow."""

    @pytest.mark.asyncio
    async def test_options_flow_updates_scan_interval(self, hass: HomeAssistant):
        """Options flow saves updated scan interval."""
        # First set up an entry
        with patch(
            "custom_components.plusnet_hub2.coordinator.PlusnetHub2Coordinator.async_validate_connection",
            new_callable=AsyncMock,
            return_value=dict(EXPECTED_DEVICES),
        ):
            result = await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=MOCK_CONFIG_DATA,
            )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        entry = result["result"]

        # Now open the options flow
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit new scan interval
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"scan_interval": 60},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["scan_interval"] == 60
