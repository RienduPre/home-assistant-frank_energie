"""Test the Frank Energie integration setup and teardown logic."""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD

from custom_components.frank_energie.const import DOMAIN

pytestmark = pytest.mark.asyncio


@pytest.fixture
def config_entry(hass: HomeAssistant) -> AsyncMock:
    """Create a mock config entry for testing."""
    entry = AsyncMock()
    entry.domain = DOMAIN
    entry.entry_id = "1234abcd"
    entry.data = {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "securepassword",
    }
    entry.title = "Frank Energie"
    entry.state = ConfigEntryState.NOT_LOADED
    return entry


async def test_setup_entry_success(hass: HomeAssistant, config_entry: AsyncMock):
    """Test successful setup of a config entry."""
    with patch(
        "custom_components.frank_energie.FrankEnergieApiClient",
        autospec=True
    ) as mock_client:
        mock_client.return_value.async_authenticate.return_value = True
        mock_client.return_value.sites = [{"id": "site-123", "name": "Home"}]

        # Patch platforms setup
        with patch(
            "custom_components.frank_energie.async_setup_platforms", return_value=True
        ) as setup_platforms:
            from custom_components.frank_energie import async_setup_entry

            result = await async_setup_entry(hass, config_entry)
            assert result is True
            assert hass.data[DOMAIN][config_entry.entry_id]["client"]
            setup_platforms.assert_called_once()


async def test_setup_entry_auth_failure(hass: HomeAssistant, config_entry: AsyncMock):
    """Test setup fails if authentication fails."""
    with patch(
        "custom_components.frank_energie.FrankEnergieApiClient",
        autospec=True
    ) as mock_client:
        mock_client.return_value.async_authenticate.return_value = False

        from custom_components.frank_energie import async_setup_entry
        result = await async_setup_entry(hass, config_entry)
        assert result is False


async def test_unload_entry(hass: HomeAssistant, config_entry: AsyncMock):
    """Test successful unload of a config entry."""
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = {
        "client": AsyncMock()
    }

    with patch(
        "custom_components.frank_energie.async_unload_platforms",
        return_value=True
    ) as unload_platforms:
        from custom_components.frank_energie import async_unload_entry
        result = await async_unload_entry(hass, config_entry)

        assert result is True
        assert config_entry.entry_id not in hass.data[DOMAIN]
        unload_platforms.assert_called_once()
