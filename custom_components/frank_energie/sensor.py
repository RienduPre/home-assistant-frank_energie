"""Frank Energie current electricity and gas price information service."""
from __future__ import annotations

import asyncio
from asyncio.windows_events import NULL
from dataclasses import dataclass
from datetime import datetime, timedelta
from lib2to3.pgen2.token import NUMBER
import logging
from typing import Callable, List, Tuple

import aiohttp
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    STATE_CLASS_MEASUREMENT,
    DEVICE_CLASS_MONETARY,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_DISPLAY_OPTIONS,
    CURRENCY_EURO,
    ENERGY_KILO_WATT_HOUR,
    VOLUME_CUBIC_METERS,
)
from homeassistant.core import HassJob, HomeAssistant
from homeassistant.helpers import event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt

DOMAIN = "Frank Energie"
NAME = "Frank Energie"
VERSION = "2"
DATA_URL = "https://frank-api.nl/graphql"
# DATA_URL = "https://frank-graphql-prod.graphcdn.app/"
# DATA_URL = "https://graphcdn.frankenergie.nl"
ICON = "mdi:currency-eur"
ATTRIBUTION = "Data provided by Frank Energie"
SCAN_INTERVAL = timedelta(minutes=1)

@dataclass
class FrankEnergieEntityDescription(SensorEntityDescription):
    """Describes Frank Energie sensor entity."""
    value_fn: Callable[[dict], StateType] = None

SENSORS: tuple[FrankEnergieEntityDescription, ...] = (
    FrankEnergieEntityDescription(
        key="elec_markup",
        name="Current electricity price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_MONETARY,
        value_fn=lambda data: sum(data['elec']),
    ),
    FrankEnergieEntityDescription(
        key="elec_lasthour",
        name="Last hour electricity price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: sum(data['elec_lasthour']),
    ),
    FrankEnergieEntityDescription(
        key="elec_nexthour",
        name="Next hour electricity price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: sum(data['elec_nexthour']),
    ),
    FrankEnergieEntityDescription(
        key="elec_market",
        name="Current electricity market price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: data['elec'][0],
    ),
    FrankEnergieEntityDescription(
        key="elec_tax",
        name="Current electricity price including tax",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: data['elec'][0] + data['elec'][1] + data['elec'][2],
    ),
    FrankEnergieEntityDescription(
        key="elec_vat",
        name="Current electricity VAT price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_MONETARY,
        value_fn=lambda data: data['elec'][1],
    ),
    FrankEnergieEntityDescription(
        key="elec_sourcing",
        name="Current electricity sourcing markup",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_MONETARY,
        value_fn=lambda data: data['elec'][2],
    ),
    FrankEnergieEntityDescription(
        key="elec_tax_only",
        name="Current electricity tax only",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        device_class=DEVICE_CLASS_MONETARY,
        value_fn=lambda data: data['elec'][3],
    ),    
    FrankEnergieEntityDescription(
        key="elec_tax_only_test",
        name="Current electricity tax only",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: data['elec_btw'],
    ),    
    FrankEnergieEntityDescription(
        key="gas_markup",
        name="Current gas price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: sum(data['gas']),
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_vat",
        name="Current gas VAT price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['gas'][1],
    ),
    FrankEnergieEntityDescription(
        key="gas_sourcing",
        name="Current gas sourcing price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['gas'][2],
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_only",
        name="Current gas tax only",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['gas'][3],
    ),
    FrankEnergieEntityDescription(
        key="gas_market",
        name="Current gas market price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: data['gas'][0],
    ),
    FrankEnergieEntityDescription(
        key="gas_tax",
        name="Current gas price including tax",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: data['gas'][0] + data['gas'][1],
    ),
    FrankEnergieEntityDescription(
        key="gas_min",
        name="Lowest gas price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: min(data['today_gas']),
    ),
    FrankEnergieEntityDescription(
        key="gas_max",
        name="Highest gas price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: max(data['today_gas']),
    ),
    FrankEnergieEntityDescription(
        key="elec_min",
        name="Lowest energy price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: min(data['today_elec']),
    ),
    FrankEnergieEntityDescription(
        key="elec_max",
        name="Highest energy price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: max(data['today_elec']),
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_min",
        name="Lowest energy price tomorrow",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(min(data['tonorrow_elec']),3),
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_max",
        name="Highest energy price tomorrow",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(max(data['tonorrow_elec']),3),
    ),
    FrankEnergieEntityDescription(
        key="elec_avg",
        name="Average electricity price today (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['today_elec']) / 24, 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_avg24",
        name="Average electricity price today (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['today_elec']) / 24, 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_avg48",
        name="Average electricity price today+tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['today_elec']) / 48, 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_avg72",
        name="Average electricity price yesterday+today+tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['today_elec']) / 72, 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_tax",
        name="Average electricity price today including tax",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['today_elec_tax']) / len(data['today_elec_tax']), 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_market",
        name="Average electricity market price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['today_elec_market']) / len(data['today_elec_market']), 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_hourcount",
        name="Number of hours with prices loaded",
        icon = "mdi:numeric-0-box-multiple",
        native_unit_of_measurement = None,
        state_class = STATE_CLASS_MEASUREMENT,
        device_class = None,
        value_fn = lambda data: len(data['elec_count']),
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg",
        name="Average electricity price tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['tonorrow_elec']) / 24, 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_tax",
        name="Average electricity price tomorrow including tax",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['tomorrow_elec_tax']) / 24, 3),
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_market",
        name="Average electricity market price tomorrow",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        state_class=STATE_CLASS_MEASUREMENT,
        value_fn=lambda data: round(sum(data['tomorrow_elec_market']) / 24, 3),
    ),
)

_LOGGER = logging.getLogger(__name__)

OPTION_KEYS = [desc.key for desc in SENSORS]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_DISPLAY_OPTIONS, default=[]): vol.All(
            cv.ensure_list, [vol.In(OPTION_KEYS)]
        ),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None) -> None:
    """Set up the Frank Energie sensors."""
    _LOGGER.debug("Setting up Frank")

    websession = async_get_clientsession(hass)

    coordinator = FrankEnergieCoordinator(hass, websession)

    entities = [
        FrankEnergieSensor(coordinator, description)
        for description in SENSORS
        if description.key in config[CONF_DISPLAY_OPTIONS]
    ]

    await coordinator.async_config_entry_first_refresh()

    async_add_entities(entities, True)


class FrankEnergieSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Frank Energie sensor."""

    _attr_device_class = DEVICE_CLASS_MONETARY
    _attr_state_class = STATE_CLASS_MEASUREMENT
    _attr_attribution = ATTRIBUTION
    _attr_icon = ICON

    def __init__(self, coordinator: FrankEnergieCoordinator, description: FrankEnergieEntityDescription) -> None:
        """Initialize the sensor."""
        self.entity_description: FrankEnergieEntityDescription = description
        self._attr_unique_id = f"{DOMAIN}.{description.key}"

        self._update_job = HassJob(self.async_schedule_update_ha_state)
        self._unsub_update = None

        super().__init__(coordinator)

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        self._attr_native_value = self.entity_description.value_fn(self.coordinator.processed_data())

        # Cancel the currently scheduled event if there is any
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None

        # Schedule the next update at exactly the next whole hour sharp
        self._unsub_update = event.async_track_point_in_utc_time(
            self.hass,
            self._update_job,
            dt.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
        )

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return {"last_updated": datetime.now()}

class FrankEnergieCoordinator(DataUpdateCoordinator):
    """Get the latest data and update the states."""

    def __init__(self, hass: HomeAssistant, websession) -> None:
        """Initialize the data object."""
        self.hass = hass
        self.websession = websession

        logger = logging.getLogger(__name__)

        super().__init__(
            hass,
            logger,
            name="Frank Energie coordinator",
            update_interval=timedelta(minutes=15),
        )

    async def _async_update_data(self) -> dict:
        """Get the latest data from Frank Energie"""
        self.logger.debug("Fetching Frank Energie data")

        # We request data for today up until the day after tomorrow.
        # This is to ensure we always request all available data.
        # New data available after 15:00

        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=2)

        query_data = {
            "query": """
                query MarketPrices($startDate: Date!, $endDate: Date!) {
                     marketPricesElectricity(startDate: $startDate, endDate: $endDate) { 
                        from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice priceMarkup priceIncludingMarkup
                     } 
                     marketPricesGas(startDate: $startDate, endDate: $endDate) { 
                        from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice priceMarkup priceIncludingMarkup
                     } 
                }
            """,
            "variables": {"startDate": str(yesterday), "endDate": str(tomorrow)},
            "operationName": "MarketPrices"
        }
        try:
            resp = await self.websession.post(DATA_URL, json=query_data)

            data = await resp.json()
            self._elec_data = data['data']['marketPricesElectricity']
            self._gas_data = data['data']['marketPricesGas']
            self._last_update = datetime.now()
            return data['data']

        except (asyncio.TimeoutError, aiohttp.ClientError, KeyError) as error:
            raise UpdateFailed(f"Fetching energy data failed: {error}") from error

    def processed_data(self):
        return {
            'elec': self.get_current_hourprice(self.data['marketPricesElectricity']),
            'elec_btw': self.get_current_btwprice(self.data['marketPricesElectricity']),
            'elec_lasthour': self.get_last_hourprice(self.data['marketPricesElectricity']),
            'elec_nexthour': self.get_next_hourprice(self.data['marketPricesElectricity']),
            'today_elec_market': self.get_hourprices_market(self.data['marketPricesElectricity']),
            'today_elec_tax': self.get_hourprices_tax(self.data['marketPricesElectricity']),
            'today_elec': self.get_hourprices(self.data['marketPricesElectricity']),
            'elec_count': self.get_hours(self.data['marketPricesElectricity']),
            'tonorrow_elec': self.get_tomorrow_prices(self.data['marketPricesElectricity']),
            'tomorrow_elec_tax': self.get_tomorrow_prices_tax(self.data['marketPricesElectricity']),
            'tomorrow_elec_market': self.get_tomorrow_prices_market(self.data['marketPricesElectricity']),
            'gas': self.get_current_hourprice(self.data['marketPricesGas']),
            'today_gas': self.get_hourprices(self.data['marketPricesGas'])
        }

    def get_last_hourprice(self, hourprices) -> Tuple:
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) < dt.utcnow() - timedelta(hours=1) < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice'], hour['energyTaxPrice']

    def get_next_hourprice(self, hourprices) -> Tuple:
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) < dt.utcnow() + timedelta(hours=1) < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice'], hour['energyTaxPrice']

    def get_current_hourprice(self, hourprices) -> Tuple:
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) < dt.utcnow() < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice'], hour['energyTaxPrice']

    def get_current_btwprice(self, hourprices) -> Tuple:
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) < dt.utcnow() < dt.parse_datetime(hour['till']):
                return hour['energyTaxPrice']

    def get_current_hourprices_tax(self, hourprices) -> Tuple:
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) < dt.utcnow() < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice']

    def get_hourprices(self, hourprices) -> List:
        yesterday_prices = []
        today_prices = []
        tomorrow_prices = []

        i=0
        for hour in hourprices:
            if i < 24:
                yesterday_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if 3 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_hours(self, hourprices) -> List:
        elec_hours = []

        for hour in hourprices:
            elec_hours.append(
                (hour['from'])
            )
        return elec_hours

    def get_hourprices_market(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'])
                )
            i=i+1
        if 3 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_hourprices_tax(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            i=i+1
        if 3 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_tomorrow_prices(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if -1 < datetime.now().hour < 15:
            return [0.000]
        if len(hourprices) == 48:
            return [0.000]
        return tomorrow_prices

    def get_tomorrow_prices_tax(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            i=i+1
        if -1 < datetime.now().hour < 15:
            return [0.000]
        if len(hourprices) == 48:
            return [0.000]
        return tomorrow_prices

    def get_tomorrow_prices_market(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'])
                )
            i=i+1
        if -1 < datetime.now().hour < 15:
            return [0.000]
        if len(hourprices) == 48:
            return [0.000]
        return tomorrow_prices
