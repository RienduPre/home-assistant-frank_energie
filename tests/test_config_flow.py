"""Tests for Frank Energie config flow."""

from typing import Any

import pytest
from aiohttp import ClientConnectionError
from syrupy.assertion import SnapshotAssertion

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.frank_energie.const import (
    CONF_ACCESS_TOKEN,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SITE,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("mock_setup_entry", "mock_setup_entry_success")

USER_INPUT = {
    CONF_USERNAME: "user@example.com",
    CONF_PASSWORD: "secure_password",
}


async def test_show_login_form(hass: HomeAssistant) -> None:
    """Test that the login form is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "login"


async def test_invalid_authentication(hass: HomeAssistant, mock_auth_failure) -> None:
    """Test showing error when authentication fails."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=USER_INPUT,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "login"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_connection_error(hass: HomeAssistant, mock_auth_exception) -> None:
    """Test handling of connection errors."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=USER_INPUT,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "login"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_successful_login_flow(hass: HomeAssistant, mock_auth_success) -> None:
    """Test a successful login and redirect to site step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=USER_INPUT,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "site"


async def test_reauth_flow_success(hass: HomeAssistant, mock_auth_success, config_entry) -> None:
    """Test successful reauthentication."""
    config_entry.async_start_reauth(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH},
        data={CONF_USERNAME: config_entry.data[CONF_USERNAME]},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "login"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={**USER_INPUT},
    )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"


async def test_options_flow_with_site(hass: HomeAssistant, config_entry_with_site, snapshot: SnapshotAssertion) -> None:
    """Test options flow when site is available."""
    result = await hass.config_entries.options.async_init(config_entry_with_site.entry_id)
    assert result == snapshot


async def test_options_flow_without_site(hass: HomeAssistant, config_entry) -> None:
    """Test options flow fallback when site is not set."""
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "You do not have to login for this entry."}


async def test_login_validation_errors(hass: HomeAssistant) -> None:
    """Test validation errors for empty username/password."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_USERNAME: "", CONF_PASSWORD: ""},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}  # fallback error for now
