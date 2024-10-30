import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from homeassistant.config_entries import ConfigEntry
from custom_components.frank_energie.const import DATA_ELECTRICITY, DATA_GAS, DATA_MONTH_SUMMARY, DATA_INVOICES, DATA_USER
from custom_components.frank_energie.coordinator import FrankEnergieCoordinator
from python_frank_energie import FrankEnergie
from python_frank_energie.models import PriceData, MonthSummary, Invoices, User

# Sample data for mocking
mock_entry_data = {
    "site_reference": "test_reference",
    "access_token": "test_token",
}

@pytest.fixture
def mock_frank_energie():
    """Create a mock FrankEnergie API instance."""
    return AsyncMock(spec=FrankEnergie)

@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return ConfigEntry(
        version=1,
        domain="frank_energie",
        title="Frank Energie",
        data=mock_entry_data,
        options={},
        source="user",
        entry_id="123",
        state="loaded",
    )

@pytest.fixture
def coordinator(mock_frank_energie, mock_config_entry):
    """Create an instance of FrankEnergieCoordinator."""
    return FrankEnergieCoordinator(
        hass=MagicMock(),
        entry=mock_config_entry,
        api=mock_frank_energie,
    )


@pytest.mark.asyncio
async def test_fetch_today_data(coordinator, mock_frank_energie):
    """Test fetching today's data."""
    # Setup mock return values
    mock_prices = PriceData(electricity=0.45, gas=0.09)
    mock_frank_energie.prices.return_value = mock_prices
    mock_frank_energie.month_summary.return_value = MonthSummary()
    mock_frank_energie.invoices.return_value = Invoices()
    mock_frank_energie.user.return_value = User()

    # Perform the fetch
    data = await coordinator._fetch_today_data(datetime.now(timezone.utc).date(), 
                                                datetime.now(timezone.utc).date() + timedelta(days=1))

    # Assertions
    assert data is not None
    assert data[DATA_ELECTRICITY] == 0.45
    assert data[DATA_GAS] == 0.09
    assert isinstance(data[DATA_MONTH_SUMMARY], MonthSummary)
    assert isinstance(data[DATA_INVOICES], Invoices)
    assert isinstance(data[DATA_USER], User)


@pytest.mark.asyncio
async def test_renew_token(coordinator, mock_frank_energie):
    """Test token renewal."""
    # Mock renewal of the token
    mock_frank_energie.renew_token.return_value = AsyncMock(authToken='new_token', refreshToken='new_refresh_token')

    await coordinator._FrankEnergieCoordinator__try_renew_token()

    # Verify that the entry data was updated with new tokens
    assert coordinator.entry.data['access_token'] == 'new_token'


@pytest.mark.asyncio
async def test_aggregate_data(coordinator):
    """Test data aggregation."""
    prices_today = PriceData(electricity=0.45, gas=0.09)
    prices_tomorrow = PriceData(electricity=0.50, gas=0.10)
    data_month_summary = MonthSummary()
    data_invoices = Invoices()
    data_user = User()

    aggregated_data = coordinator._aggregate_data(prices_today, prices_tomorrow, 
                                                  data_month_summary, data_invoices, data_user)

    # Assertions
    assert aggregated_data[DATA_ELECTRICITY] == 0.95  # 0.45 + 0.50
    assert aggregated_data[DATA_GAS] == 0.19  # 0.09 + 0.10
    assert isinstance(aggregated_data[DATA_MONTH_SUMMARY], MonthSummary)
    assert isinstance(aggregated_data[DATA_INVOICES], Invoices)
    assert isinstance(aggregated_data[DATA_USER], User)

