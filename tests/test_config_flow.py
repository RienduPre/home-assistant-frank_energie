import pytest
from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant
from custom_components.frank_energie.const import DOMAIN, CONF_ACCESS_TOKEN, CONF_TOKEN


@pytest.fixture
async def mock_auth_success():
    class MockAuth:
        authToken = "access_token"
        refreshToken = "refresh_token"

    return MockAuth()


async def test_show_login_form(hass: HomeAssistant) -> None:
    """Test that the login form is shown initially."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "login"


async def test_invalid_login(hass: HomeAssistant) -> None:
    """Test showing errors when login fails."""
    # Patch de login methode zodat deze altijd faalt
    with pytest.MonkeyPatch().context() as mp:
        from custom_components.frank_energie.config_flow import FrankEnergieConfigFlow
        mp.setattr(FrankEnergieConfigFlow, "_authenticate", lambda *_, **__: None)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": "user", "password": ""},
        )

        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}


async def test_successful_login(hass: HomeAssistant, mock_auth_success) -> None:
    """Test a successful login and flow continuation."""
    with pytest.MonkeyPatch().context() as mp:
        from custom_components.frank_energie.config_flow import FrankEnergieConfigFlow

        async def _mock_authenticate(self, user_input):
            return mock_auth_success

        async def _mock_step_site(self, sign_in_data):
            return self.async_create_entry(title="Frank Energie", data=sign_in_data)

        mp.setattr(FrankEnergieConfigFlow, "_authenticate", _mock_authenticate)
        mp.setattr(FrankEnergieConfigFlow, "async_step_site", _mock_step_site)

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={"username": "testuser", "password": "testpass"},
        )

        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["title"] == "Frank Energie"
        assert result["data"]["username"] == "testuser"
        assert result["data"][CONF_ACCESS_TOKEN] == "access_token"
        assert result["data"][CONF_TOKEN] == "refresh_token"


async def test_options_flow_with_site(hass: HomeAssistant) -> None:
    """Test that options flow is shown when a site is configured."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user", "site": "123"},
        options={}
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_options_flow_no_site(hass: HomeAssistant) -> None:
    """Test that NoOptionsAvailableFlowHandler is shown if no site is selected."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user"},
        options={}
    )
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"
    assert result["errors"] == {"base": "You do not have to login for this entry."}


class MockConfigEntry:
    """Mock config entry for testing purposes."""

    def __init__(self, domain: str, data: dict, options: dict) -> None:
        self.domain = domain
        self.data = data
        self.options = options
        self.entry_id = "1234"

    def add_to_hass(self, hass: HomeAssistant) -> None:
        hass.config_entries._entries.append(self)
