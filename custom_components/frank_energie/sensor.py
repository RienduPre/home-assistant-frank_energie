"""Frank Energie current electricity and gas price information service."""
from __future__ import annotations

import asyncio
import logging
import socket
import aiohttp
from aiohttp.hdrs import METH_GET, METH_POST
import async_timeout
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Final, List, Tuple

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (PLATFORM_SCHEMA,
                                             SensorDeviceClass, SensorEntity,
                                             SensorEntityDescription,
                                             SensorStateClass)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (CONF_DISPLAY_OPTIONS, CONF_NAME, PERCENTAGE,
                                 CURRENCY_EURO, ENERGY_KILO_WATT_HOUR,
                                 VOLUME_CUBIC_METERS, CONF_FILENAME, CONF_HOST)
from homeassistant.core import HassJob, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType, StateType
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator,
                                                      UpdateFailed)
from homeassistant.util import dt

from .const import (_LOGGER, ATTRIBUTION, CONF_COORDINATOR, DEFAULT_NAME,
                    DOMAIN, ICON, NAME, PLATFORMS, SCAN_INTERVAL, SENSORS,
                    VERSION, FrankEnergieEntityDescription, DATA_ELECTRICITY,
                    DATA_GAS, DATA_URL, DEFAULT_ROUND)
from .coordinator import FrankEnergieCoordinator
from .entity import FrankEnergieEntity
from .price_data import PriceData

LOGGER = logging.getLogger(__name__)
_LOGGER = logging.getLogger(__name__)

DOMAIN: Final = "Frank Energie"
NAME: Final = "Frank Energie"
DEFAULT_NAME = NAME
VERSION: Final = "2022.11.25"
DATA_URL = "https://frank-graphql-prod.graphcdn.app"
DATA_URL = "https://graphcdn.frankenergie.nl"
DATA_URL = "https://frank-api.nl/graphql"
#DATA_URL : Final = "https://frank-api.nl/graphql","https://frank-graphql-prod.graphcdn.app","https://graphcdn.frankenergie.nl"
API_TIMEOUT = 10
API_TIMEZONE: Final = "Europe/Amsterdam"
ICON: Final = "mdi:currency-eur"
ATTRIBUTION: Final = "Data provided by Frank Energie"
MANUFACTURER: Final = "Frank Energie B.V."
UNIQUE_ID: Final = f"{DOMAIN}_component"
COMPONENT_TITLE: Final = "Frank Energie"
SCAN_INTERVAL: Final[timedelta] = timedelta(minutes=1)
#UPDATE_INTERVAL: Final[timedelta] = timedelta(minutes=60)
UPDATE_INTERVAL = timedelta(minutes=60)
ATTR_HOUR: Final = "Hour"
ATTR_TIME: Final = "Time"
DEFAULT_ROUND = 3
DATA_ELECTRICITY = "electricity"
DATA_GAS = "gas"
component_status = "init"

@dataclass
class FrankEnergieEntityDescription(SensorEntityDescription):
    """Describes Frank Energie sensor entity."""
    value_fn: Callable[[dict], StateType] = None
    attr_fn: Callable[[dict[str, Any]], dict[str, StateType]] = lambda _: {}
    value_fn: Callable[[dict[PriceData]], StateType] = None
    attr_fn: Callable[[dict[PriceData]], dict[str, StateType]] = lambda _: {}

SENSORS: tuple[FrankEnergieEntityDescription, ...] = (
    FrankEnergieEntityDescription(
        key="elec_markup",
        name="Current electricity price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: sum(data['elec']),
        attr_fn=lambda data: data['elec_market_upcoming_attr'],
    ),
    FrankEnergieEntityDescription(
        key="elec_lasthour",
        name="Last hour electricity price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['elec_lasthour']),DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_nexthour",
        name="Next hour electricity price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['elec_nexthour']),DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_market",
        name="Current electricity market price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: float(data['elec'][1]) / 9 * 100,
    ),
    FrankEnergieEntityDescription(
        key="elec_tax",
        name="Current electricity price including tax and markup",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: data['elec'][0] + data['elec'][1] + data['elec'][2],
    ),
    FrankEnergieEntityDescription(
        key="elec_vat",
        name="Current electricity VAT price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: float(data['elec'][1]),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_sourcing",
        name="Current electricity sourcing markup",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(data['elec'][2],DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_tax_only",
        name="Current electricity tax only",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(data['elec'][3],DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),    
    FrankEnergieEntityDescription(
        key="elec_market_percent_tax",
        name="Electricity market percent tax",
        native_unit_of_measurement=PERCENTAGE,
        device_class = None,
        icon="mdi:percent",
        value_fn=lambda data: data['elec'][1] / (float(data['elec'][1]) / 9 * 100 / 100),
        entity_registry_enabled_default=False,
    ),    
    FrankEnergieEntityDescription(
        key="elec_min",
        name="Lowest energy price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(min(data['today_elec'].values()),DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_TIME: min(data['today_elec'],key=data['today_elec'].get)},
    ),
    FrankEnergieEntityDescription(
        key="elec_max",
        name="Highest energy price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(max(data['today_elec'].values()),DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_TIME: max(data['today_elec'],key=data['today_elec'].get)},
    ),
    FrankEnergieEntityDescription(
        key="elec_upcoming_min",
        name="Lowest energy price upcoming hours",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(min(data['elec_market_upcoming'].values()),DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_TIME: min(data['elec_market_upcoming'],key=data['elec_market_upcoming'].get)},
    ),
    FrankEnergieEntityDescription(
        key="elec_upcoming_max",
        name="Highest energy price upcoming hours",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(max(data['elec_market_upcoming'].values()),DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_TIME: max(data['elec_market_upcoming'],key=data['elec_market_upcoming'].get)},
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_min",
        name="Lowest energy price tomorrow",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(data['tomorrow_elec_min'],DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_TIME: data['tomorrow_elec_min_time']},
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_max",
        name="Highest energy price tomorrow",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(data['tomorrow_elec_max'],DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_TIME: data['tomorrow_elec_max_time']},
    ),
    FrankEnergieEntityDescription(
        key="elec_avg",
        name="Average electricity price today (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['today_elec'].values()) / len(data['today_elec'].values()), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['today_elec'].values())},
    ),
    FrankEnergieEntityDescription(
        key="gas_avg",
        name="Average gas price today (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(sum(data['today_gas']) / len(data['today_gas']), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['today_gas'])},
    ),
    FrankEnergieEntityDescription(
        key="elec_avg24",
        name="Average electricity price today (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['today_elec'].values()) / 24, DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_avg48",
        name="Average electricity price today+tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['today_elec'].values()) / 48, DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_avg72",
        name="Average electricity price yesterday+today+tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['today_elec'].values()) / 72, DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_tax",
        name="Average electricity price today including tax",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['today_elec_tax']) / len(data['today_elec_tax']), DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_market",
        name="Average electricity market price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['today_elec_market']) / len(data['today_elec_market']), DEFAULT_ROUND),
    ),
    FrankEnergieEntityDescription(
        key="elec_hourcount",
        name="Number of hours with prices loaded",
        icon="mdi:numeric-0-box-multiple",
        device_class = "",
        value_fn=lambda data: data['elec_count'],
        entity_registry_enabled_default=False,
        entity_registry_visible_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_hourcount",
        name="Number of hours for gas with prices loaded",
        icon="mdi:numeric-0-box-multiple",
        device_class="",
        value_fn=lambda data: data['gas_count'],
        entity_registry_enabled_default=False,
        entity_registry_visible_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg",
        name="Average electricity price tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: data['tomorrow_elec_avg'],
    ),
    FrankEnergieEntityDescription(
        key="elec_upcoming_avg_market",
        name="Average electricity price upcoming (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: round(sum(data['elec_market_upcoming'].values()) / len(data['elec_market_upcoming'].values()), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['elec_market_upcoming'].values())},
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_tax",
        name="Average electricity price tomorrow including tax",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: data['tomorrow_elec_tax'],
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_market",
        name="Average electricity market price tomorrow",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{ENERGY_KILO_WATT_HOUR}",
        value_fn=lambda data: data['tomorrow_elec_market'],
    ),
    FrankEnergieEntityDescription(
        key="gas_markup",
        name="Current gas price (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(sum(data['gas']),DEFAULT_ROUND),
        attr_fn=lambda data: data['gas_market_upcoming_attr'],
    ),
    FrankEnergieEntityDescription(
        key="gas_markup_before6am",
        name="Gas price before 6AM (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(sum(data['today_gas_before6am']) / len(data['today_gas_before6am']), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['today_gas_before6am'])},
    ),
    FrankEnergieEntityDescription(
        key="gas_markup_after6am",
        name="Gas price after 6AM (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(sum(data['today_gas_after6am']) / len(data['today_gas_after6am']), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['today_gas_after6am'])},
    ),
    FrankEnergieEntityDescription(
        key="gas_market",
        name="Current gas market price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['gas'][0],
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_vat",
        name="Current gas VAT price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(data['gas'][1],DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_sourcing",
        name="Current gas sourcing price",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['gas'][2],
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_only",
        name="Current gas tax only",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['gas'][3],
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_tax",
        name="Current gas price including tax and markup",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(data['gas'][0] + data['gas'][1] + data['gas'][2],DEFAULT_ROUND),
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_min",
        name="Lowest gas price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(min(data['today_gas']),DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_HOUR: data['today_gas'].index(min(data['today_gas'])),ATTR_TIME:datetime.now().replace(hour=data['today_gas'].index(min(data['today_gas'])), minute=0, second=0, microsecond=0)},
    ),
    FrankEnergieEntityDescription(
        key="gas_max",
        name="Highest gas price today",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(max(data['today_gas']),DEFAULT_ROUND),
        attr_fn=lambda data: {ATTR_HOUR: data['today_gas'].index(max(data['today_gas'])),ATTR_TIME:datetime.now().replace(hour=data['today_gas'].index(max(data['today_gas'])), minute=0, second=0, microsecond=0)},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow",
        name="Gas price tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(sum(data['tonorrow_gas']) / len(data['tonorrow_gas']), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['tonorrow_gas'])},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_avg",
        name="Average gas price tomorrow (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: round(sum(data['tonorrow_gas']) / len(data['tonorrow_gas']), DEFAULT_ROUND),
        attr_fn=lambda data: {"Number of hours": len(data['tonorrow_gas'])},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_after6am",
        name="Gas price tomorrow after 6AM (All-in)",
        native_unit_of_measurement=f"{CURRENCY_EURO}/{VOLUME_CUBIC_METERS}",
        value_fn=lambda data: data['tonorrow_gas_after6am'],
    ),
)

OPTION_KEYS = [desc.key for desc in SENSORS]

CONF_ALLOW_UNREACHABLE = "allow_unreachable"
DEFAULT_UNREACHABLE = False

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_DISPLAY_OPTIONS, default=[]): vol.All(
            cv.ensure_list, [vol.In(OPTION_KEYS)]
        ),
        vol.Optional(CONF_ALLOW_UNREACHABLE, default=DEFAULT_UNREACHABLE): cv.boolean,
    }
)

async def async_setup_platform(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the Frank Energie component from a config entry."""

    # Initialise the coordinator and save it as domain-data
    web_session_client = async_get_clientsession(hass)
    frank_coordinator = FrankEnergieCoordinator(hass, web_session_client)

    device_info = DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=NAME,
        name=NAME,
        model=VERSION,
        configuration_url="https://www.frankenergie.nl",
    )

    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        #hass.data.setdefault(DOMAIN, {})[entry.entry_id] = frank_coordinator
        hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_COORDINATOR: frank_coordinator,
    }

    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            frank_coordinator.platforms.append(platform)
            hass.async_add_job(
                hass.config_entries.async_forward_entry_setup(entry, platform)
            )

    # Fetch initial data, so we have data when entities subscribe and set up the platform
    await frank_coordinator.async_config_entry_first_refresh()

    if not frank_coordinator.last_update_success:
        raise ConfigEntryNotReady

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the Frank Energie sensors."""
    _LOGGER.debug("Setting up Frank")

    web_session_client = async_get_clientsession(hass)
    frank_coordinator = FrankEnergieCoordinator(hass, web_session_client)
    #frank_coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]
    await frank_coordinator.async_refresh()

    if not frank_coordinator.last_update_success:
        raise ConfigEntryNotReady

    entities = [
        FrankEnergieSensor(hass, frank_coordinator, description)
        for description in SENSORS
        #if description.key in config[CONF_DISPLAY_OPTIONS]
    ]

    await frank_coordinator.async_config_entry_first_refresh()

    async_add_entities(entities, True)

class FrankEnergieSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Frank Energie sensor."""
    
    # Default settings for all sensors.
    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_attribution = ATTRIBUTION
    _attr_icon = ICON

    def __init__(self, hass: HomeAssistant, coordinator: FrankEnergieCoordinator, description: FrankEnergieEntityDescription) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.entity_description: FrankEnergieEntityDescription = description
        self._attr_unique_id = f"{DOMAIN}.{description.key}"

        # Exceptions for non default sensors.
        if not f"{description.device_class}":
            self._attr_device_class = f"{description.icon}"
        if not f"{description.icon}":
            self._attr_icon = f"{description.icon}"

        self._update_job = HassJob(self.async_schedule_update_ha_state)
        #self._update_job = HassJob(self._handle_scheduled_update)
        self._unsub_update = None

        super().__init__(coordinator)

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        try:
            self._attr_native_value = self.entity_description.value_fn(self.coordinator.processed_data())
        except (TypeError, IndexError, ValueError):
            # No data available
            self._attr_native_value = "unavailable"
            #self._attr_native_value = None

        # Cancel the currently scheduled event if there is any
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None

        # Schedule the next update at exactly the next whole hour sharp
        #dt.utcnow().replace(minute=0, second=0) + timedelta(hours=1),
        self._unsub_update = event.async_track_point_in_utc_time(
            self.hass,
            self._update_job,
            dt.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
        )

    async def _handle_scheduled_update(self, _):
        """ Handle a scheduled update. """
        # Only handle the scheduled update for entities which have a reference to hass,
        # which disabled sensors don't have.
        if self.hass is None:
            return

        self.async_schedule_update_ha_state(True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self.entity_description.attr_fn(self.coordinator.processed_data())
        return self.entity_description.attr_fn(self.coordinator.data)

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
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        """Get the latest data from Frank Energie"""
        self.logger.debug("Fetching Frank Energie data")

        # We request data for today up until the day after tomorrow.
        # This is to ensure we always request all available data.
        # New data available after 15:00

        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        day_after_tomorrow = today + timedelta(days=2)

        try:
            data_yesterday = await self._run_graphql_query(yesterday, today)
            data_today = await self._run_graphql_query(today, tomorrow)
            data_tomorrow = await self._run_graphql_query(tomorrow, day_after_tomorrow)
        except UpdateFailed as err:
            # Check if we still have data to work with, if so, return this data. Still log the error as warning
            if self.data[DATA_ELECTRICITY].get_future_prices() and self.data[DATA_GAS].get_future_prices():
                LOGGER.warning(str(err))
                return self.data
            # Re-raise the error if there's no data from future left
            raise err

        if data_yesterday and data_tomorrow:
            return {
                'marketPricesElectricity': data_yesterday['marketPricesElectricity'] + data_today['marketPricesElectricity'] + data_tomorrow['marketPricesElectricity'],
                'marketPricesGas': data_today['marketPricesGas'] + data_tomorrow['marketPricesGas'],
                DATA_ELECTRICITY: PriceData(
                    data_yesterday.get('marketPricesElectricity', []) + data_today.get('marketPricesElectricity', []) + data_tomorrow.get('marketPricesElectricity', [])
                ),
                DATA_GAS: PriceData(
                    data_yesterday.get('marketPricesElectricity', []) + data_today.get('marketPricesGas', []) + data_tomorrow.get('marketPricesGas', [])
                ),
            }

        if data_tomorrow:
            return {
                'marketPricesElectricity': data_today['marketPricesElectricity'] + data_tomorrow['marketPricesElectricity'],
                'marketPricesGas': data_today['marketPricesGas'] + data_tomorrow['marketPricesGas'],
                DATA_ELECTRICITY: PriceData(
                    data_today.get('marketPricesElectricity', []) + data_tomorrow.get('marketPricesElectricity', [])
                ),
                DATA_GAS: PriceData(
                    data_today.get('marketPricesGas', []) + data_tomorrow.get('marketPricesGas', [])
                ),
            }

        return {
            'marketPricesElectricity': data_today['marketPricesElectricity'],
            'marketPricesGas': data_today['marketPricesGas'],
            DATA_ELECTRICITY: PriceData(
                data_today.get('marketPricesElectricity', [])
            ),
            DATA_GAS: PriceData(
                data_today.get('marketPricesGas', [])
            ),
        }  

    async def _run_graphql_query(self, start_date, end_date) -> dict:
        query_data = {
            "query": """
                query MarketPrices($startDate: Date!, $endDate: Date!) {
                     marketPricesElectricity(startDate: $startDate, endDate: $endDate) { 
                        from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice
                     } 
                     marketPricesGas(startDate: $startDate, endDate: $endDate) { 
                        from till marketPrice marketPriceTax sourcingMarkupPrice energyTaxPrice
                     } 
                }
            """,
            "variables": {"startDate": str(start_date), "endDate": str(end_date)},
            "operationName": "MarketPrices"
        }
        try:
            url = DATA_URL
            response = await self.websession.post(DATA_URL, json=query_data)
            data = await response.json()
            return data['data'] if data['data'] else {}

        except (asyncio.TimeoutError) as exception:
            _LOGGER.error(
                "Timeout error fetching information from %s - %s",
                url,
                exception,
            )

        except (KeyError, TypeError) as exception:
            _LOGGER.error(
                "Error parsing information from %s - %s",
                url,
                exception,
            )
        except (aiohttp.ClientError, socket.gaierror) as exception:
            _LOGGER.error(
                "Error fetching information from %s - %s",
                url,
                exception,
            )

        except FrankEnergieApiException as exception:
            _LOGGER.error("Error in API! - %s", exception)
            # Raise to pass on to the user.
            raise exception

        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.error("Something really wrong happened! - %s", exception)
            raise UpdateFailed(f"Fetching energy data for period {start_date} - {end_date} failed: {error}") from error

    def processed_data(self):
        return {
            'elec': self.get_current_hourprice(self.data['marketPricesElectricity']),
            'elec_lasthour': self.get_last_hourprice(self.data['marketPricesElectricity']),
            'elec_nexthour': self.get_next_hourprice(self.data['marketPricesElectricity']),
            'elec_market_upcoming': self.get_upcoming_prices(self.data['marketPricesElectricity']),
            'elec_market_upcoming_attr': self.get_upcoming_prices_attr(self.data['marketPricesElectricity']),
            'today_elec_market': self.get_hourprices_market(self.data['marketPricesElectricity']),
            'today_elec_tax': self.get_hourprices_tax(self.data['marketPricesElectricity']),
            'today_elec': self.get_hourprices(self.data['marketPricesElectricity']),
            'elec_count': len(self.data['marketPricesElectricity']),
            'tonorrow_elec': self.get_tomorrow_prices(self.data['marketPricesElectricity']),
            'tomorrow_elec_tax': self.get_tomorrow_prices_tax(self.data['marketPricesElectricity']),
            'tomorrow_elec_market': self.get_tomorrow_prices_market(self.data['marketPricesElectricity']),
            'tomorrow_elec_min': self.get_min_tomorrow_prices(self.data['marketPricesElectricity']),
            'tomorrow_elec_max': self.get_max_tomorrow_prices(self.data['marketPricesElectricity']),
            'tomorrow_elec_avg': self.get_avg_tomorrow_prices(self.data['marketPricesElectricity']),
            'tomorrow_elec_time': self.get_tomorrow_prices_time(self.data['marketPricesElectricity']),
            'tomorrow_elec_min_time': self.get_tomorrow_prices_min_time(self.data['marketPricesElectricity']),
            'tomorrow_elec_max_time': self.get_tomorrow_prices_max_time(self.data['marketPricesElectricity']),
            'gas_count': len(self.data['marketPricesGas']),
            'gas': self.get_current_hourprice(self.data['marketPricesGas']),
            'today_gas': self.get_hourprices_gas(self.data['marketPricesGas']),
            'today_gas_before6am': self.get_hourprices_gas_before6am(self.data['marketPricesGas']),
            'today_gas_after6am': self.get_hourprices_gas_after6am(self.data['marketPricesGas']),
            'tonorrow_gas': self.get_tomorrow_prices_gas(self.data['marketPricesGas']),
            'tonorrow_gas_after6am': self.get_tomorrow_prices_gas_after6am(self.data['marketPricesGas']),
            'gas_market_upcoming_attr': self.get_upcoming_prices_attr(self.data['marketPricesGas']),
            'status': component_status,
        }

    def get_last_hourprice(self, hourprices) -> Tuple:
        if len(hourprices) == 0: #fix when no data for today is available
            return 'unavailable'
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) <= dt.utcnow() - timedelta(hours=1) < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice'], hour['energyTaxPrice']

    def get_next_hourprice(self, hourprices) -> Tuple:
        if len(hourprices) == 0: #fix when no data for today is available
            return 'unavailable'
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) <= dt.utcnow() + timedelta(hours=1) < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice'], hour['energyTaxPrice']

    def get_current_hourprice(self, hourprices) -> Tuple:
        if len(hourprices) == 0: #fix when no data for today is available
            return 'unavailable'
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) <= dt.utcnow() < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice'], hour['energyTaxPrice']

    def get_current_btwprice(self, hourprices) -> Tuple:
        if len(hourprices) == 0: #fix when no data for today is available
            return 'unavailable'
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) <= dt.utcnow() < dt.parse_datetime(hour['till']):
                return hour['energyTaxPrice']

    def get_current_hourprices_tax(self, hourprices) -> Tuple:
        if len(hourprices) == 0: #fix when no data for today is available
            return 'unavailable'
        for hour in hourprices:
            if dt.parse_datetime(hour['from']) <= dt.utcnow() < dt.parse_datetime(hour['till']):
                return hour['marketPrice'], hour['marketPriceTax'], hour['sourcingMarkupPrice']

    def get_hourprices(self, hourprices) -> Dict:
        if len(hourprices) == 0: #fix when no data for today is available
            return 'unavailable'
        today_prices = dict()
        today_prices1 = dict()
        extrahour_prices = dict()
        extrahour_prices2 = dict()
        tomorrow_prices = dict()
        i=0
        for hour in hourprices:
            # Calling astimezone(None) automagically gets local timezone
            fromtime = dt.parse_datetime(hour['from']).astimezone()
            if -1 < i < 24:
               today_prices[fromtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
            if 23 < i < 48:
               today_prices1[fromtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
            if 24 < i < 49:
               extrahour_prices[fromtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
            if 47 < i < 72:
               tomorrow_prices[fromtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
            if 48 < i < 73:
               extrahour_prices2[fromtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
            i=i+1
        if len(hourprices) is 24:
            return today_prices
        if len(hourprices) is 49:
            return extrahour_prices
        if len(hourprices) is 73:
            return extrahour_prices2
        if 3 < datetime.now().hour < 24:
            return today_prices1
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices1

    def get_hourprices_gas(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []
        
        i=0
        for hour in hourprices:
            if i < 24:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 48:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if len(hourprices) == 48:
            return tomorrow_prices
        if 5 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            return today_prices
        if len(hourprices) == 30:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_hourprices_gas_before6am(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []

        i=0
        for hour in hourprices:
            if i < 6:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 30:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if len(hourprices) is 30:
            return today_prices
        if 5 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_hourprices_gas_after6am(self, hourprices) -> List:
        today_prices = []
        tomorrow_prices = []

        i=0
        for hour in hourprices:
            if 5 < i < 30:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 29 < i < 48:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if len(hourprices) is 30:
            return today_prices
        if 5 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_hourprices_market(self, hourprices) -> List:
        #if len(hourprices) == 24: #fix when no data for today is available
        #    return 'unavailable'
        extrahour_prices = []
        today_prices = []
        today_prices2 = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if -1 < i < 24:
                today_prices2.append(
                    (hour['marketPrice'])
                )
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'])
                )
            if 24 < i < 49:
                extrahour_prices.append(
                    (hour['marketPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'])
                )
            i=i+1
        if len(hourprices) is 24:
            return today_prices2
        if len(hourprices) is 49:
            return extrahour_prices
        if 3 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_hourprices_tax(self, hourprices) -> List:
        #if len(hourprices) == 24: #fix when no data for today is available
        #    return 'unavailable'
        extrahour_prices = []
        today_prices = []
        today_prices2 = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if -1 < i < 24:
                today_prices2.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            if 23 < i < 48:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            if 24 < i < 49:
                extrahour_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'])
                )
            i=i+1
        if len(hourprices) is 24:
            return today_prices2
        if len(hourprices) is 49:
            return extrahour_prices
        if 3 < datetime.now().hour < 24:
            return today_prices
        if -1 < datetime.now().hour < 3:
            if tomorrow_prices:
                return tomorrow_prices
        return today_prices

    def get_tomorrow_prices(self, hourprices) -> List:
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if len(hourprices) > 71:
            return tomorrow_prices
        return 'unavailable'

    def get_avg_tomorrow_prices(self, hourprices) -> List:
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 47 < i < 72:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if -1 < datetime.now().hour < 15:
            return 'unavailable'
        if len(hourprices) is 24:
            UPDATE_INTERVAL = timedelta(minutes=5)
        if len(hourprices) > 71:
            UPDATE_INTERVAL = timedelta(minutes=60)
            if tomorrow_prices:
                return round(sum(tomorrow_prices) / len(tomorrow_prices), DEFAULT_ROUND)
        #if tomorrow_prices:
        #    return round(sum(tomorrow_prices) / len(tomorrow_prices), DEFAULT_ROUND)
        return 'unavailable'

    def get_min_tomorrow_prices(self, hourprices) -> List:
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
            return 'unavailable'
        if len(hourprices) is 72:
            return round(min(tomorrow_prices), DEFAULT_ROUND)
        if len(hourprices) is 48:
            return 'unavailable'
        if tomorrow_prices:
            return round(min(tomorrow_prices), DEFAULT_ROUND)

    def get_max_tomorrow_prices(self, hourprices) -> List:
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
            return 'unavailable'
        if len(hourprices) is 72:
            return round(max(tomorrow_prices), DEFAULT_ROUND)
        if len(hourprices) is 48:
            return 'unavailable'
        if tomorrow_prices:
            return round(max(tomorrow_prices), DEFAULT_ROUND)

    def get_tomorrow_prices_time(self, hourprices) -> Dict:
        today_prices = dict()
        tomorrow_prices = dict()
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices[hour['from']] = (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
            if 47 < i < 72:
                tomorrow_prices[hour['from']] = (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
            i=i+1
        if -1 < datetime.now().hour < 15:
            return 'unavailable'
        if len(hourprices) is 48:
            return 'unavailable'
        if len(hourprices) is 72:
            return tomorrow_prices
        return tomorrow_prices

    def get_tomorrow_prices_min_time(self, hourprices) -> Dict:
        today_prices = dict()
        tomorrow_prices = dict()
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices[hour['from']] = (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
            if 47 < i < 72:
                tomorrow_prices[hour['from']] = (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
            i=i+1
        if -1 < datetime.now().hour < 15:
            return '—'
        if len(hourprices) is 48:
            return '—'
        if len(hourprices) is 72:
            return min(tomorrow_prices,key=tomorrow_prices.get)
        if tomorrow_prices:
            return min(tomorrow_prices,key=tomorrow_prices.get)

    def get_tomorrow_prices_max_time(self, hourprices) -> Dict:
        today_prices = dict()
        tomorrow_prices = dict()
        i=0
        for hour in hourprices:
            if 23 < i < 48:
                today_prices[hour['from']] = (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
            if 47 < i < 72:
                tomorrow_prices[hour['from']] = (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
            i=i+1
        if -1 < datetime.now().hour < 15:
            return '—'
        if len(hourprices) is 48:
            return '—'
        if len(hourprices) is 72:
            return max(tomorrow_prices,key=tomorrow_prices.get)
        if tomorrow_prices:
            return max(tomorrow_prices,key=tomorrow_prices.get)

    def get_tomorrow_prices_gas(self, hourprices) -> List:
        today_prices = []
        today_prices2 = []
        tomorrow_prices = []
        tomorrow_prices2 = []
        tomorrow_before6am_prices = []
        i=0
        for hour in hourprices:
            if 5 < i < 24:
                today_prices2.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 30:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 48:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 29 < i < 48:
                tomorrow_prices2.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 41 < i < 48:
                tomorrow_before6am_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if len(hourprices) is 48:
            return tomorrow_prices2
        if len(hourprices) is 24:
            return today_prices2
        if -1 < datetime.now().hour < 3:
            return today_prices
        if 5 < datetime.now().hour < 15:
            return today_prices
        if 15 < datetime.now().hour < 24:
            return tomorrow_prices
        if len(hourprices) is 30:
            return today_prices
        return tomorrow_prices

    def get_tomorrow_prices_gas_after6am(self, hourprices) -> List:
        if len(hourprices) is 24:
            return "unavailable"
        today_prices = []
        tomorrow_prices = []
        tomorrow_after6am_prices = []
        tomorrow_after6am_prices2 = []
        i=0
        for hour in hourprices:
            if 23 < i < 30:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 11 < i < 30:
                tomorrow_after6am_prices2.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 48:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 29 < i < 48:
                tomorrow_after6am_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if -1 < datetime.now().hour < 22:
            return "unavailable"
        if len(hourprices) is 48:
            return round(sum(tomorrow_after6am_prices) / len(tomorrow_after6am_prices), DEFAULT_ROUND)
        #if 21 < datetime.now().hour < 24:
        #    return "unavailable"
            #round(sum(tomorrow_after6am_prices) / len(tomorrow_after6am_prices), DEFAULT_ROUND)
        if len(hourprices) is 30:
            return round(sum(tomorrow_after6am_prices2) / len(tomorrow_after6am_prices2), DEFAULT_ROUND)
        return round(sum(tomorrow_after6am_prices) / len(tomorrow_after6am_prices), DEFAULT_ROUND)

    def get_tomorrow_prices_gas_avg_not_used(self, hourprices) -> List:
        today_prices = []
        today_prices2 = []
        tomorrow_prices = []
        i=0
        for hour in hourprices:
            if 5 < i < 24:
                today_prices2.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 23 < i < 30:
                today_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            if 42 < i < 48:
                tomorrow_prices.append(
                    (hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice'])
                )
            i=i+1
        if len(hourprices) is 24:
            return today_prices2
        if 5 < datetime.now().hour < 15:
            return today_prices
        if len(hourprices) is 48:
            return tomorrow_prices
        if len(hourprices) is 30:
            return today_prices
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
            return "unavailable"
        if len(hourprices) is 48:
            return "unavailable"
        if tomorrow_prices:
            return round(sum(tomorrow_prices) / len(tomorrow_prices), DEFAULT_ROUND)
        return "unavailable"

    def get_tomorrow_prices_market(self, hourprices) -> List:
        if -1 < datetime.now().hour < 15:
            return "unavailable"
        if len(hourprices) is 48:
            return "unavailable"

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
        if tomorrow_prices:
            return round(sum(tomorrow_prices) / len(tomorrow_prices), DEFAULT_ROUND)

    def get_upcoming_prices(self, hourprices) -> Dict:
        upcoming_prices = dict()
        now = datetime.utcnow()
        for hour in hourprices:
            if datetime.fromisoformat(hour['from'][:-5]) > now:
               fromtime = dt.parse_datetime(hour['from']).astimezone()
               upcoming_prices[fromtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
        return upcoming_prices

    def get_upcoming_prices_attr(self, hourprices) -> List:
        upcoming_prices = {}
        now = datetime.utcnow()
        for hour in hourprices:
            #utcfromtime = datetime.fromisoformat(hour['from'][:-5])
            utcfromtime = dt.parse_datetime(hour['from'][:-5])
            if utcfromtime > now:
                utctime = dt.parse_datetime(hour['from'])
                # Convert to local time for display in attribute
                localtime = dt.as_local(utctime)
                upcoming_prices[localtime] = hour['marketPrice'] + hour['marketPriceTax'] + hour['sourcingMarkupPrice'] + hour['energyTaxPrice']
        return upcoming_prices

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)

class FrankEnergieApiException(Exception):
    """Frank Energie API Exception class"""
