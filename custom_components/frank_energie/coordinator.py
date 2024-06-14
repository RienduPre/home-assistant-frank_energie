""" Coordinator implementation for Frank Energie integration.
    Fetching the latest data from Frank Energie and updating the states."""
# coordinator.py

import asyncio
import sys
from datetime import date, datetime, time, timedelta
from typing import Callable, Optional, TypedDict

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)
from python_frank_energie import FrankEnergie
from python_frank_energie.exceptions import AuthException, RequestException
from python_frank_energie.models import (Invoices, MarketPrices, MonthSummary,
                                         PriceData, User)

from .const import (_LOGGER, DATA_ELECTRICITY, DATA_GAS, DATA_INVOICES,
                    DATA_MONTH_SUMMARY, DATA_USER, DeviceResponseEntry)

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class FrankEnergieData(TypedDict):
    """ Represents data fetched from Frank Energie API. """
    DATA_ELECTRICITY: PriceData
    """Electricity price data."""

    DATA_GAS: PriceData

    """Gas price data."""

    DATA_MONTH_SUMMARY: Optional[MonthSummary]
    """Optional summary data for the month."""

    DATA_INVOICES: Optional[Invoices]
    """Optional invoices data."""

    DATA_USER: Optional[User]
    """Optional user data."""


class FrankEnergieCoordinator(DataUpdateCoordinator[DeviceResponseEntry]):
    """ Get the latest data and update the states. """

    api: FrankEnergie

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: FrankEnergie
    ) -> None:
        """Initialize the data object."""
        self.hass = hass
        self.entry = entry
        self.api = api
        self.site_reference = entry.data.get("site_reference", None)

        super().__init__(
            hass,
            _LOGGER,
            name="Frank Energie coordinator",
            update_interval=timedelta(minutes=60),
        )

    async def _async_update_data(self) -> FrankEnergieData:
        """Get the latest data from Frank Energie."""

        # We request data for today up until the day after tomorrow.
        # This is to ensure we always request all available data.
        today = datetime.utcnow().date()
        tomorrow = today + timedelta(days=1)
        day_after_tomorrow = tomorrow + timedelta(days=1)
        prices_tomorrow = None

        # Fetch data for today and tomorrow separately,
        # because the gas prices response only contains data for the first day of the query
        try:
            _LOGGER.debug("Fetching Frank Energie data for today %s", self.entry.entry_id)
            prices_today = await self.__fetch_prices_with_fallback(today, tomorrow)

            data_month_summary = (
                await self.api.month_summary(self.site_reference) if self.api.is_authenticated else None
            )
            data_invoices = (
                await self.api.invoices(self.site_reference) if self.api.is_authenticated else None
            )
            data_user = (
                await self.api.user(self.site_reference) if self.api.is_authenticated else None
            )
            _LOGGER.debug("Data user: %s", data_user)

        except UpdateFailed as err:
            # Check if we still have data to work with, if so, return this data. Still log the error as warning
            if (
                self.coordinator.data[DATA_ELECTRICITY].get_future_prices()
                and self.coordinator.data[DATA_GAS].get_future_prices()
            ):
                _LOGGER.warning(str(err))
                # Return old values from coordinator
                return self.coordinator.data
            # Re-raise the error if there's no data from future left
            raise err

        except RequestException as ex:
            if str(ex).startswith("user-error:"):
                raise ConfigEntryAuthFailed from ex
            raise UpdateFailed(ex) from ex

        except AuthException as ex:
            _LOGGER.debug("Authentication tokens expired, trying to renew them (%s)", ex)
            await self.__try_renew_token()
            # Tell we have no data, so update coordinator tries again with renewed tokens
            raise UpdateFailed(ex) from ex

        try:
            # Only fetch data for tomorrow after 13:00 UTC
            if datetime.utcnow().hour >= 13:
                _LOGGER.debug("Fetching Frank Energie data for tomorrow")
                prices_tomorrow = await self.__fetch_prices_with_fallback(tomorrow, day_after_tomorrow)
            else:
                prices_tomorrow = None
        except UpdateFailed as err:
            _LOGGER.debug("Error fetching Frank Energie data for tomorrow (%s)", err)
            # Handle the exception for prices_tomorrow
            # You can log a warning, return available data, or re-raise the error as needed
            pass  # Add your handling logic here
        except AuthException as ex:
            _LOGGER.debug("Authentication tokens expired, trying to renew them (%s)", ex)
            await self.__try_renew_token()
            raise UpdateFailed(ex) from ex

        # return FrankEnergieData()
        if prices_tomorrow is not None:
            return {
                DATA_ELECTRICITY: prices_today.electricity + prices_tomorrow.electricity,
                DATA_GAS: prices_today.gas + prices_tomorrow.gas,
                DATA_MONTH_SUMMARY: data_month_summary,
                DATA_INVOICES: data_invoices,
                DATA_USER: data_user,
            }
        else:
            return {
                DATA_ELECTRICITY: prices_today.electricity,
                DATA_GAS: prices_today.gas,
                DATA_MONTH_SUMMARY: data_month_summary,
                DATA_INVOICES: data_invoices,
                DATA_USER: data_user,
            }

    async def __fetch_prices_with_fallback(self, start_date: date, end_date: date) -> MarketPrices:
        """Fetch prices with fallback mechanism."""

        if not self.api.is_authenticated:
            return await self.api.prices(start_date, end_date)

        # user_prices = await self.api.user_prices(start_date, end_date)
        user_prices = await self.api.user_prices(start_date, self.site_reference, end_date)

        # if len(user_prices.gas.all) > 0 and len(user_prices.electricity.all) > 0:
        if user_prices.gas.all and user_prices.electricity.all:
            # If user_prices are available for both gas and electricity return them
            return user_prices

        public_prices = await self.api.prices(start_date, end_date)

        # Use public prices if no user prices are available
        if len(user_prices.gas.all) == 0:
            # if user_prices.gas.all is None:
            _LOGGER.info("No gas prices found for user, falling back to public prices")
            user_prices.gas = public_prices.gas

        if len(user_prices.electricity.all) == 0:
            # if user_prices.electricity.all is None:
            _LOGGER.info("No electricity prices found for user, falling back to public prices")
            user_prices.electricity = public_prices.electricity

        return user_prices

    async def __try_renew_token(self):
        """Try to renew authentication token."""

        try:
            updated_tokens = await self.api.renew_token()

            data = {
                CONF_ACCESS_TOKEN: updated_tokens.authToken,
                CONF_TOKEN: updated_tokens.refreshToken,
            }
            # Update the config entry with the new tokens
            self.hass.config_entries.async_update_entry(self.entry, data=data)

            _LOGGER.debug("Successfully renewed token")

        except AuthException as ex:
            _LOGGER.error("Failed to renew token: %s. Starting user reauth flow", ex)
            # Consider setting the coordinator to an error state or handling the error appropriately
            raise ConfigEntryAuthFailed from ex


async def run_hourly(start_time: datetime, end_time: datetime, interval: timedelta, method: Callable) -> None:
    """Run the specified method at regular intervals between start_time and end_time."""
    while True:
        now = datetime.now().time()
        if start_time <= now <= end_time:
            await method()
        # await asyncio.sleep(interval.total_seconds())
        await asyncio.sleep(interval)


async def hourly_refresh(coordinator: FrankEnergieCoordinator) -> None:
    """Perform hourly refresh of coordinator."""
    await coordinator.async_refresh()


async def start_coordinator(hass: HomeAssistant) -> None:
    """Start the coordinator."""
    async with aiohttp.ClientSession() as session:
        coordinator = FrankEnergieCoordinator(hass, session)
        await coordinator.async_refresh()

        start_time = time(15, 0)
        end_time = time(16, 0)
        interval = timedelta(minutes=5)

        await run_hourly(start_time, end_time, interval, lambda: hourly_refresh(coordinator))
