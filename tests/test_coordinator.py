import pytest
from unittest.mock import AsyncMock, patch
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from python_frank_energie import FrankEnergie
from python_frank_energie.exceptions import AuthException, RequestException
from .coordinator import FrankEnergieCoordinator, FrankEnergieData

@pytest.fixture
def mock_frank_energie():
    """Mock the FrankEnergie API."""
    return AsyncMock(spec=FrankEnergie)

@pytest.fixture
def mock_config_entry():
    """Mock the config entry."""
    return ConfigEntry(
        entry_id="1",
        domain="frank_energie",
        title="Frank Energie",
        data={"access_token": "test_token", "site_reference": "test_site_ref"},
        state="loaded",
    )

@pytest.fixture
def coordinator(hass: HomeAssistant, mock_frank_energie, mock_config_entry):
    """Create a FrankEnergieCoordinator instance."""
    coordinator = FrankEnergieCoordinator(hass, mock_config_entry, mock_frank_energie)
    return coordinator

@pytest.mark.asyncio
async def test_coordinator_initialization(coordinator):
    """Test coordinator initialization."""
    assert coordinator.hass is not None
    assert coordinator.entry.entry_id == "1"
    assert coordinator.api is not None

@pytest.mark.asyncio
async def test_fetch_today_data_success(coordinator, mock_frank_energie):
    """Test fetching today's data successfully."""
    mock_frank_energie.is_authenticated = True
    mock_frank_energie.month_summary.return_value = AsyncMock()
    mock_frank_energie.invoices.return_value = AsyncMock()
    mock_frank_energie.user.return_value = AsyncMock()
    mock_frank_energie.prices.return_value = AsyncMock()

    data = await coordinator._fetch_today_data(datetime.now().date(), datetime.now().date() + timedelta(days=1))

    assert data is not None
    assert mock_frank_energie.month_summary.called
    assert mock_frank_energie.invoices.called
    assert mock_frank_energie.user.called
    assert mock_frank_energie.prices.called

@pytest.mark.asyncio
async def test_fetch_today_data_auth_error(coordinator, mock_frank_energie):
    """Test handling of authentication error when fetching today's data."""
    mock_frank_energie.is_authenticated = False

    with pytest.raises(AuthException):
        await coordinator._fetch_today_data(datetime.now().date(), datetime.now().date() + timedelta(days=1))

@pytest.mark.asyncio
async def test_token_renewal_success(coordinator, mock_frank_energie):
    """Test token renewal."""
    mock_frank_energie.renew_token.return_value = AsyncMock(authToken='new_token', refreshToken='new_refresh')

    await coordinator._FrankEnergieCoordinator__try_renew_token()

    assert mock_frank_energie.renew_token.called
    assert coordinator.entry.data[CONF_ACCESS_TOKEN] == 'new_token'

@pytest.mark.asyncio
async def test_token_renewal_failure(coordinator, mock_frank_energie):
    """Test token renewal failure."""
    mock_frank_energie.renew_token.side_effect = AuthException("Failed to renew token")

    with pytest.raises(AuthException):
        await coordinator._FrankEnergieCoordinator__try_renew_token()

@pytest.mark.asyncio
async def test_aggregate_data(coordinator):
    """Test data aggregation."""
    prices_today = AsyncMock()
    prices_today.electricity = 0.20
    prices_today.gas = 0.05

    prices_tomorrow = AsyncMock()
    prices_tomorrow.electricity = 0.25
    prices_tomorrow.gas = 0.04

    data_month_summary = AsyncMock()
    data_invoices = AsyncMock()
    data_user = AsyncMock()

    aggregated_data = coordinator._aggregate_data(prices_today, prices_tomorrow, data_month_summary, data_invoices, data_user)

    assert aggregated_data[DATA_ELECTRICITY] == 0.45
    assert aggregated_data[DATA_GAS] == 0.09
    assert aggregated_data[DATA_MONTH_SUMMARY] == data_month_summary
    assert aggregated_data[DATA_INVOICES] == data_invoices
    assert aggregated_data[DATA_USER] == data_user

# More tests can be added as necessary...
