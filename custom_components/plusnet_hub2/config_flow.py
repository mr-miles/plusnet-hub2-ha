"""Config flow for Plusnet Hub 2 / BT Smart Hub 2 integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
)
from .coordinator import (
    PlusnetHub2AuthError,
    PlusnetHub2ConnectionError,
    PlusnetHub2Coordinator,
)

_LOGGER = logging.getLogger(__name__)


class PlusnetHub2ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plusnet Hub 2."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — get host / credentials from the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip().rstrip("/")
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "")

            # Prevent duplicate entries for the same host
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()

            # Validate by actually connecting
            from homeassistant.config_entries import ConfigEntry as _CE  # noqa: F401

            # We need a temporary entry-like object to build the coordinator.
            # Use a simple namespace instead.
            import types

            fake_entry = types.SimpleNamespace(
                data={
                    CONF_HOST: host,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                },
                options={},
            )

            coordinator = PlusnetHub2Coordinator(self.hass, fake_entry)  # type: ignore[arg-type]

            try:
                devices = await coordinator.async_validate_connection()
                _LOGGER.debug(
                    "Config flow: connected to hub, found %d devices", len(devices)
                )
            except PlusnetHub2AuthError:
                errors["base"] = "invalid_auth"
            except PlusnetHub2ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error during config flow validation")
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title=f"Plusnet Hub 2 ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                    vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): str,
                    vol.Optional(CONF_PASSWORD, default=""): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "default_host": DEFAULT_HOST,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return PlusnetHub2OptionsFlow(config_entry)


class PlusnetHub2OptionsFlow(OptionsFlow):
    """Handle options for the Plusnet Hub 2 integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_scan_interval: int = self._config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self._config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_scan_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                }
            ),
        )
