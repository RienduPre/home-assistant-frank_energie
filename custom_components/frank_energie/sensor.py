"""Frank Energie current electricity and gas price information service."""
# sensor.py
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from homeassistant.components.sensor import (SensorDeviceClass, SensorEntity,
                                             SensorEntityDescription,
                                             SensorStateClass)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_EURO, FORMAT_DATE, PERCENTAGE
from homeassistant.core import HassJob, HomeAssistant
from homeassistant.helpers import event
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt, utcnow

from .const import (_LOGGER, API_CONF_URL, ATTR_TIME, ATTRIBUTION,
                    COMPONENT_TITLE, CONF_COORDINATOR, DATA_ELECTRICITY,
                    DATA_GAS, DATA_INVOICES, DATA_MONTH_SUMMARY, DATA_USER,
                    DOMAIN, ICON, SERVICE_NAME_COSTS, SERVICE_NAME_PRICES,
                    SERVICE_NAME_USER, UNIT_ELECTRICITY, UNIT_GAS, VERSION)
from .coordinator import FrankEnergieCoordinator

FORMAT_DATE = "%d-%m-%Y"

@dataclass
class FrankEnergieEntityDescription(SensorEntityDescription):
    """Describes Frank Energie sensor entity."""

    authenticated: bool = False
    service_name: str | None = SERVICE_NAME_PRICES
    value_fn: Callable[[dict], StateType] = None
    attr_fn: Callable[[dict], dict[str, StateType | list]] = lambda _: {}


SENSOR_TYPES: tuple[FrankEnergieEntityDescription, ...] = (
    FrankEnergieEntityDescription(
        key="elec_markup",
        name="Current electricity price (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.total,
        attr_fn=lambda data: {"prices": data[DATA_ELECTRICITY].asdict("total", timezone="Europe/Amsterdam")},
    ),
    FrankEnergieEntityDescription(
        key="elec_market",
        name="Current electricity market price",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.market_price,
        attr_fn=lambda data: {"prices": data[DATA_ELECTRICITY].asdict("market_price")},
    ),
    FrankEnergieEntityDescription(
        key="elec_tax",
        name="Current electricity price including tax",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.market_price_with_tax,
        attr_fn=lambda data: {
            "prices": data[DATA_ELECTRICITY].asdict("market_price_with_tax")
        },
    ),
    FrankEnergieEntityDescription(
        key="elec_tax_vat",
        name="Current electricity VAT price",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.market_price_tax,
        attr_fn=lambda data: {'prices': data[DATA_ELECTRICITY].asdict('market_price_tax')},
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_sourcing",
        name="Current electricity sourcing markup",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.sourcing_markup_price,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_tax_only",
        name="Current electricity tax only",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.energy_tax_price,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_markup",
        name="Current gas price (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].current_hour.total,
        attr_fn=lambda data: {"prices": data[DATA_GAS].asdict("total")},
    ),
    FrankEnergieEntityDescription(
        key="gas_market",
        name="Current gas market price",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].current_hour.market_price,
        attr_fn=lambda data: {"prices": data[DATA_GAS].asdict("market_price")},
    ),
    FrankEnergieEntityDescription(
        key="gas_tax",
        name="Current gas price including tax",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].current_hour.market_price_with_tax,
        attr_fn=lambda data: {"prices": data[DATA_GAS].asdict("market_price_with_tax")},
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_vat",
        name="Current gas VAT price",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].current_hour.market_price_tax,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_sourcing",
        name="Current gas sourcing price",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].current_hour.sourcing_markup_price,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_only",
        name="Current gas tax only",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].current_hour.energy_tax_price,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_min",
        name="Lowest gas price today (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].today_min.total,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_GAS].today_min.date_from},
    ),
    FrankEnergieEntityDescription(
        key="gas_max",
        name="Highest gas price today (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_GAS].today_max.total,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_GAS].today_max.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_min",
        name="Lowest electricity price today (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].today_min.total,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].today_min.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_max",
        name="Highest electricity price today (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=4,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].today_max.total,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].today_max.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_avg",
        name="Average electricity price today (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data[DATA_ELECTRICITY].today_avg,
        attr_fn=lambda data: {
            'Number of hours': len(data[DATA_ELECTRICITY].get_today_prices),
            'prices': data[DATA_ELECTRICITY].asdict('total', today_only=True, timezone="Europe/Amsterdam")},
    ),
    FrankEnergieEntityDescription(
        key="elec_previoushour",
        name="Previous hour electricity price (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        value_fn=lambda data: data[DATA_ELECTRICITY].previous_hour.total if data[DATA_ELECTRICITY].previous_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_nexthour",
        name="Next hour electricity price (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        suggested_display_precision=3,
        value_fn=lambda data: data[DATA_ELECTRICITY].next_hour.total if data[DATA_ELECTRICITY].next_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_market_percent_tax",
        name="Electricity market percent tax",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class = '',
        icon="mdi:percent",
        value_fn = lambda data: (100 / (data[DATA_ELECTRICITY].current_hour.market_price / data[DATA_ELECTRICITY].current_hour.market_price_tax)) if data[DATA_ELECTRICITY].current_hour.market_price != 0 and data[DATA_ELECTRICITY].current_hour.market_price_tax != 0 else 21,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_market_percent_tax",
        name="Gas market percent tax",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class = '',
        icon="mdi:percent",
        value_fn = lambda data: (100 / (data[DATA_GAS].current_hour.market_price / data[DATA_GAS].current_hour.market_price_tax)) if data[DATA_GAS].current_hour.market_price != 0 and data[DATA_GAS].current_hour.market_price_tax != 0 else 21,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_all_min",
        name="Lowest electricity price all hours (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].all_min.total,
        suggested_display_precision=4,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].all_min.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_all_max",
        name="Highest electricity price all hours (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].all_max.total,
        suggested_display_precision=4,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].all_max.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_min",
        name="Lowest electricity price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].tomorrow_min.total if data[DATA_ELECTRICITY].tomorrow_min else None,
        suggested_display_precision=4,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].tomorrow_min.date_from} if data[DATA_ELECTRICITY].tomorrow_min else None,
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_max",
        name="Highest electricity price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].tomorrow_max.total if data[DATA_ELECTRICITY].tomorrow_max else None,
        suggested_display_precision=4,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].tomorrow_max.date_from} if data[DATA_ELECTRICITY].tomorrow_max else None,
    ),
    FrankEnergieEntityDescription(
        key="elec_upcoming_min",
        name="Lowest electricity price upcoming hours (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_min.total,
        suggested_display_precision=4,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].upcoming_min.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_upcoming_max",
        name="Highest electricity price upcoming hours (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_max.total,
        suggested_display_precision=4,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_ELECTRICITY].upcoming_max.date_from},
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_tax",
        name="Average electricity price today including tax",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].today_tax_avg,
        entity_registry_enabled_default=True,
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_tax_markup",
        name="Average electricity price today including tax and markup",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].today_tax_markup_avg,
        entity_registry_enabled_default=True,
    ),
    FrankEnergieEntityDescription(
        key="elec_avg_market",
        name="Average electricity market price today",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].today_market_avg,
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_tax_markup",
        name="Average electricity price tomorrow including tax and markup",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].get_tomorrow_average_price_including_tax_and_markup,
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg",
        name="Average electricity price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].get_tomorrow_average_price() if data[DATA_ELECTRICITY].get_tomorrow_average_price() else None,
        attr_fn=lambda data: {'tomorrow_prices': data[DATA_ELECTRICITY].asdict('total', tomorrow_only=True, timezone="Europe/Amsterdam")},
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_tax",
        name="Average electricity price tomorrow including tax",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].get_tomorrow_average_price_including_tax(),
    ),
    FrankEnergieEntityDescription(
        key="elec_tomorrow_avg_market",
        name="Average electricity market price tomorrow",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].get_tomorrow_average_market_price(),
    ),
    FrankEnergieEntityDescription(
        key="elec_market_upcoming",
        name="Average electricity market price upcoming",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_avg.marketPrice,
        attr_fn=lambda data: {'upcoming_prices': data[DATA_ELECTRICITY].asdict('marketPrice', upcoming_only=True)},
    ),
    FrankEnergieEntityDescription(
        key="elec_upcoming",
        name="Average electricity price upcoming (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_avg.total,
        #attr_fn=lambda data: {'upcoming_prices': data[DATA_ELECTRICITY].asdict('total', upcoming_only=True)},
        attr_fn=lambda data: data[DATA_ELECTRICITY].upcoming_attr,
    ),
    FrankEnergieEntityDescription(
        key="elec_all",
        name="Average electricity price all hours (All-in)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].all_avg.total,
        #attr_fn=lambda data: {'upcoming_prices': data[DATA_ELECTRICITY].asdict('total')},
        attr_fn=lambda data: data[DATA_ELECTRICITY].all_attr,
    ),
    FrankEnergieEntityDescription(
        key="elec_tax_markup",
        name="Current electricity price including tax and markup",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].current_hour.market_price_including_tax_and_markup,
        attr_fn=lambda data: {'prices': data[DATA_ELECTRICITY].asdict('market_price_including_tax_and_markup')},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_avg",
        name="Average gas price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].get_tomorrow_average_price(),
        entity_registry_enabled_default=False
    ),
    FrankEnergieEntityDescription(
        key="gas_tax_markup",
        name="Current gas price including tax and markup",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].current_hour.market_price_including_tax_and_markup,
        attr_fn=lambda data: {'prices': data[DATA_GAS].asdict('market_price_including_tax_and_markup')},
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_hourcount",
        name="Number of hours with electricity prices loaded",
        icon="mdi:numeric-0-box-multiple",
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        device_class = "None",
        value_fn=lambda data: data[DATA_ELECTRICITY].length,
        entity_registry_enabled_default=False,
        entity_registry_visible_default=True,
    ),
    FrankEnergieEntityDescription(
        key="gas_hourcount",
        name="Number of hours with gas prices loaded",
        icon="mdi:numeric-0-box-multiple",
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        device_class="None",
        value_fn=lambda data: data[DATA_GAS].length,
        entity_registry_enabled_default=False,
        entity_registry_visible_default=True,
    ),
    FrankEnergieEntityDescription(
        key="elec_previoushour_market",
        name="Previous hour electricity market price",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].previous_hour.market_price if data[DATA_ELECTRICITY].previous_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="elec_nexthour_market",
        name="Next hour electricity market price",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].next_hour.market_price if data[DATA_ELECTRICITY].next_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_previoushour_all_in",
        name="Previous hour gas price (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].previous_hour.total if data[DATA_GAS].previous_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_nexthour_all_in",
        name="Next hour gas price (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=4,
        value_fn=lambda data: data[DATA_GAS].next_hour.total if data[DATA_GAS].next_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_previoushour_market",
        name="Previous hour gas market price",
        native_unit_of_measurement=UNIT_GAS,
        suggested_display_precision=4,
        value_fn=lambda data: data[DATA_GAS].previous_hour.marketPrice if data[DATA_GAS].previous_hour else None,
        entity_registry_enabled_default=False,
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_avg_market",
        name="Average gas market price tomorrow",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].get_tomorrow_prices_market,
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_avg_market_tax",
        name="Average gas market price incl tax tomorrow",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].get_tomorrow_prices_market_tax,
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_avg_market_tax_markup",
        name="Average gas market price incl tax and markup tomorrow",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].get_tomorrow_prices_market_tax_markup,
    ),
    FrankEnergieEntityDescription(
        key="gas_today_avg_all_in",
        name="Average gas price today (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].get_today_prices_total,
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_avg_all_in",
        name="Average gas price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].get_tomorrow_prices_total,
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_min",
        name="Lowest gas price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].tomorrow_min.total if data[DATA_GAS].tomorrow_min else None,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_GAS].tomorrow_min.date_from if data[DATA_GAS].tomorrow_min else None},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_max",
        name="Highest gas price tomorrow (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].tomorrow_max.total if data[DATA_GAS].tomorrow_max else None,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_GAS].tomorrow_max.date_from if data[DATA_GAS].tomorrow_max else None},
    ),
    FrankEnergieEntityDescription(
        key="gas_market_upcoming",
        name="Average gas market price upcoming hours",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].upcoming_avg.marketPrice,
        attr_fn=lambda data: {'prices': data[DATA_GAS].asdict('marketPrice')},
    ),
    FrankEnergieEntityDescription(
        key="gas_upcoming_min",
        name="Lowest gas price upcoming hours (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].upcoming_min.total,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_GAS].upcoming_min.date_from},
    ),
    FrankEnergieEntityDescription(
        key="gas_upcoming_max",
        name="Highest gas price upcoming hours (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: data[DATA_GAS].upcoming_max.total,
        attr_fn=lambda data: {ATTR_TIME: data[DATA_GAS].upcoming_max.date_from},
    ),
    FrankEnergieEntityDescription(
        key="average_electricity_price_upcoming_all_in",
        name="Average electricity price upcoming (All-in)",
        translation_key="average_electricity_price_upcoming_all_in",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_avg.total,
        attr_fn=lambda data: {
            "Number of hours": len(data[DATA_ELECTRICITY].upcoming_avg.values),
            'average_electricity_price_upcoming_all_in': data[DATA_ELECTRICITY].upcoming_avg.total,
            'average_electricity_market_price_including_tax_and_markup_upcoming': data[DATA_ELECTRICITY].upcoming_avg.market_price_with_tax_and_markup,
            'average_electricity_market_markup_price': data[DATA_ELECTRICITY].upcoming_avg.market_markup_price,
            'average_electricity_market_price_including_tax_upcoming': data[DATA_ELECTRICITY].upcoming_avg.market_price_with_tax,
            'average_electricity_market_price_tax_upcoming': data[DATA_ELECTRICITY].upcoming_avg.marketPriceTax,
            'average_electricity_market_price_upcoming': data[DATA_ELECTRICITY].upcoming_avg.marketPrice,
            'upcoming_prices': data[DATA_ELECTRICITY].asdict('total', upcoming_only=True),
        }
    ),
    FrankEnergieEntityDescription(
        key="average_electricity_price_upcoming_market",
        name="Average electricity price (upcoming, market)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_market_avg,
        attr_fn=lambda data: {'average_electricity_price_upcoming_market': data[DATA_ELECTRICITY].upcoming_market_avg,
                              'upcoming_market_prices': data[DATA_ELECTRICITY].asdict('marketPrice', upcoming_only=True)
                              },
    ),
    FrankEnergieEntityDescription(
        key="average_electricity_price_upcoming_market_tax",
        name="Average electricity price (upcoming, market and tax)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_market_tax_avg,
        attr_fn=lambda data: {'average_electricity_price_upcoming_market_tax': data[DATA_ELECTRICITY].upcoming_market_tax_avg,
                              'upcoming_market_tax_prices': data[DATA_ELECTRICITY].asdict('market_price_with_tax', upcoming_only=True)
                              },
    ),
    FrankEnergieEntityDescription(
        key="average_electricity_price_upcoming_market_tax_markup",
        name="Average electricity price (upcoming, market, tax and markup)",
        native_unit_of_measurement=UNIT_ELECTRICITY,
        value_fn=lambda data: data[DATA_ELECTRICITY].upcoming_market_tax_markup_avg,
        attr_fn=lambda data: {'average_electricity_price_upcoming_market_tax_markup': data[DATA_ELECTRICITY].upcoming_market_tax_markup_avg},
    ),
    FrankEnergieEntityDescription(
        key="gas_markup_before6am",
        name="Gas price before 6AM (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: sum(data[DATA_GAS].today_gas_before6am) / len(data[DATA_GAS].today_gas_before6am),
        attr_fn=lambda data: {"Number of hours": len(data[DATA_GAS].today_gas_before6am)},
    ),
    FrankEnergieEntityDescription(
        key="gas_markup_after6am",
        name="Gas price after 6AM (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: sum(data[DATA_GAS].today_gas_after6am) / len(data[DATA_GAS].today_gas_after6am),
        attr_fn=lambda data: {"Number of hours": len(data[DATA_GAS].today_gas_after6am)},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_before6am",
        name="Gas price tomorrow before 6AM (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: (sum(data[DATA_GAS].tomorrow_gas_before6am) / len(data[DATA_GAS].tomorrow_gas_before6am)) if data[DATA_GAS].tomorrow_gas_before6am else None,
        attr_fn=lambda data: {"Number of hours": len(data[DATA_GAS].tomorrow_gas_before6am)},
    ),
    FrankEnergieEntityDescription(
        key="gas_tomorrow_after6am",
        name="Gas price tomorrow after 6AM (All-in)",
        native_unit_of_measurement=UNIT_GAS,
        value_fn=lambda data: (sum(data[DATA_GAS].tomorrow_gas_after6am) / len(data[DATA_GAS].tomorrow_gas_after6am)) if data[DATA_GAS].tomorrow_gas_after6am else None,
        attr_fn=lambda data: {"Number of hours": len(data[DATA_GAS].tomorrow_gas_after6am)},
    ),
    FrankEnergieEntityDescription(
        key="actual_costs_until_last_meter_reading_date",
        name="Actual monthly cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[
            DATA_MONTH_SUMMARY
        ].actualCostsUntilLastMeterReadingDate,
        attr_fn=lambda data: {
            "Last update": data[DATA_MONTH_SUMMARY].lastMeterReadingDate
        },
    ),
    FrankEnergieEntityDescription(
        key="expected_costs_until_last_meter_reading_date",
        name="Expected monthly cost until now",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[
            DATA_MONTH_SUMMARY
        ].expectedCostsUntilLastMeterReadingDate,
        attr_fn=lambda data: {
            "Last update": data[DATA_MONTH_SUMMARY].lastMeterReadingDate
        },
    ),
    FrankEnergieEntityDescription(
        key="difference_costs_until_last_meter_reading_date",
        name="Difference expected and actual monthly cost until now",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[
            DATA_MONTH_SUMMARY
        ].differenceUntilLastMeterReadingDate,
        attr_fn=lambda data: {
            "Last update": data[DATA_MONTH_SUMMARY].lastMeterReadingDate
        },
    ),
    FrankEnergieEntityDescription(
        key="expected_costs_this_month",
        name="Expected cost this month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_MONTH_SUMMARY].expectedCosts,
        attr_fn=lambda data: {
            "Description": data[DATA_INVOICES].currentPeriodInvoice.PeriodDescription,
        },
    ),
    FrankEnergieEntityDescription(
        key="expected_costs_per_day_this_month",
        name="Expected cost per day this month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_MONTH_SUMMARY].expectedCostsPerDay,
        attr_fn=lambda data: {
            "Last update": data[DATA_MONTH_SUMMARY].lastMeterReadingDate,
            "Description": data[DATA_INVOICES].currentPeriodInvoice.PeriodDescription,
        },
    ),
    FrankEnergieEntityDescription(
        key="costs_per_day_till_now_this_month",
        name="Cost per day till now this month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_MONTH_SUMMARY].CostsPerDayTillNow,
        attr_fn=lambda data: {
            "Last update": data[DATA_MONTH_SUMMARY].lastMeterReadingDate,
            "Description": data[DATA_INVOICES].currentPeriodInvoice.PeriodDescription,
        },
    ),
    FrankEnergieEntityDescription(
        key="invoice_previous_period",
        name="Invoice previous period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].previousPeriodInvoice.TotalAmount
        if data[DATA_INVOICES].previousPeriodInvoice
        else None,
        attr_fn=lambda data: {
            "Start date": data[DATA_INVOICES].previousPeriodInvoice.StartDate,
            "Description": data[DATA_INVOICES].previousPeriodInvoice.PeriodDescription,
        },
    ),
    FrankEnergieEntityDescription(
        key="invoice_current_period",
        name="Invoice current period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].currentPeriodInvoice.TotalAmount
        if data[DATA_INVOICES].currentPeriodInvoice
        else None,
        attr_fn=lambda data: {
            "Start date": data[DATA_INVOICES].currentPeriodInvoice.StartDate,
            "Description": data[DATA_INVOICES].currentPeriodInvoice.PeriodDescription,
        },
    ),
    FrankEnergieEntityDescription(
        key="invoice_upcoming_period",
        name="Invoice upcoming period",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].upcomingPeriodInvoice.TotalAmount
        if data[DATA_INVOICES].upcomingPeriodInvoice
        else None,
        attr_fn=lambda data: {
            "Start date": data[DATA_INVOICES].upcomingPeriodInvoice.StartDate,
            "Description": data[DATA_INVOICES].upcomingPeriodInvoice.PeriodDescription,
        },
    ),
    FrankEnergieEntityDescription(
        key="costs_this_year",
        name="Costs this year",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].TotalCostsThisYear
        if data[DATA_INVOICES].TotalCostsThisYear
        else None,
        attr_fn=lambda data: {'Invoices': data[DATA_INVOICES].AllInvoicesDictForThisYear},
    ),
    FrankEnergieEntityDescription(
        key="total_costs",
        name="Total costs",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: sum(
            invoice.TotalAmount for invoice in data[DATA_INVOICES].allPeriodsInvoices
        )
        if data[DATA_INVOICES].allPeriodsInvoices
        else None,
        attr_fn=lambda data: {
            "First meter reading": dt.parse_date(data[DATA_USER].firstMeterReadingDate).strftime(FORMAT_DATE),
            "Last meter reading": dt.parse_date(data[DATA_USER].lastMeterReadingDate).strftime(FORMAT_DATE),
            "Invoices": data[DATA_INVOICES].AllInvoicesDict,
        },
    ),
    FrankEnergieEntityDescription(
        key="average_costs_per_month",
        name="Average costs per month",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].calculate_average_costs_per_month()
        if data[DATA_INVOICES].allPeriodsInvoices
        else None,
    ),
    FrankEnergieEntityDescription(
        key="average_costs_per_month_previous_year",
        name="Average costs per month previous year",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].calculate_average_costs_per_month(dt.now().year-1)
        if data[DATA_INVOICES].allPeriodsInvoices
        else None,
    ),
    FrankEnergieEntityDescription(
        key="average_costs_per_month_this_year",
        name="Average costs per month this year",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].calculate_average_costs_per_month(dt.now().year)
        if data[DATA_INVOICES].allPeriodsInvoices
        else None,
    ),
    FrankEnergieEntityDescription(
        key="costs_previous_year",
        name="Costs previous year",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_COSTS,
        value_fn=lambda data: data[DATA_INVOICES].TotalCostsPreviousYear
        if data[DATA_INVOICES].TotalCostsPreviousYear
        else None,
        attr_fn=lambda data: {'Invoices': data[DATA_INVOICES].AllInvoicesDictForPreviousYear},
    ),
    FrankEnergieEntityDescription(
        key="advanced_payment_amount",
        name="Advanced payment amount",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=CURRENCY_EURO,
        suggested_display_precision=2,
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].advancedPaymentAmount
        if data[DATA_USER].advancedPaymentAmount
        else None,
    ),
    FrankEnergieEntityDescription(
        key="has_CO2_compensation",
        name="Has CO₂ compensation",
        icon="mdi:molecule-co2",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].hasCO2Compensation
        if data[DATA_USER].hasCO2Compensation
        else False,
    ),
    FrankEnergieEntityDescription(
        key="reference",
        name="Reference",
        icon="mdi:numeric",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].reference
        if data[DATA_USER].reference
        else None,
        attr_fn=lambda data: data[DATA_USER].delivery_sites,
    ),
    FrankEnergieEntityDescription(
        key="status",
        name="Status",
        icon="mdi:connection",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].status
        if data[DATA_USER].status
        else None,
        attr_fn=lambda data: {'Connections status': data[DATA_USER].connectionsStatus},
    ),
    FrankEnergieEntityDescription(
        key="firstMeterReadingDate",
        name="First meter reading date",
        icon="mdi:calendar-clock",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: dt.parse_date(data[DATA_USER].firstMeterReadingDate).strftime(FORMAT_DATE)
        if data[DATA_USER].firstMeterReadingDate
        else None,
    ),
    FrankEnergieEntityDescription(
        key="lastMeterReadingDate",
        name="Last meter reading date",
        icon="mdi:calendar-clock",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: dt.parse_date(data[DATA_USER].lastMeterReadingDate).strftime(FORMAT_DATE)
        if data[DATA_USER].lastMeterReadingDate
        else None,
    ),
    FrankEnergieEntityDescription(
        key="treesCount",
        name="Trees count",
        icon="mdi:tree-outline",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].treesCount
        if not data[DATA_USER].treesCount is None
        else 0,
    ),
    FrankEnergieEntityDescription(
        key="friendsCount",
        name="Friends count",
        icon="mdi:account-group",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].friendsCount
        if not data[DATA_USER].friendsCount is None
        else None,
    ),
    FrankEnergieEntityDescription(
        key="deliverySite",
        name="Delivery Site",
        icon="mdi:home",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].format_delivery_site_as_dict[0],
        attr_fn=lambda data: next(iter(data[DATA_USER].delivery_site_as_dict.values())),
    ),
    FrankEnergieEntityDescription(
        key="rewardPayoutPreference",
        name="Reward payout preference",
        icon="mdi:numeric",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].UserSettings.get("rewardPayoutPreference")
        if data[DATA_USER].UserSettings
        else None,
    ),
    FrankEnergieEntityDescription(
        key="PushNotificationPriceAlerts",
        name="Push notification price alerts",
        icon="mdi:trophy-outline",
        authenticated=True,
        service_name=SERVICE_NAME_USER,
        value_fn=lambda data: data[DATA_USER].PushNotificationPriceAlerts[0]["isEnabled"]
        if data[DATA_USER].PushNotificationPriceAlerts
        else None,
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Frank Energie sensor entries."""
    frank_coordinator = hass.data[DOMAIN][config_entry.entry_id][CONF_COORDINATOR]
    timezone = hass.config.time_zone
    # Add an entity for each sensor type, when authenticated is True,
    # only add the entity if the user is authenticated
    async_add_entities(
        [
            FrankEnergieSensor(frank_coordinator, description, config_entry)
            for description in SENSOR_TYPES
            if not description.authenticated or frank_coordinator.api.is_authenticated
        ],
        True,
    )


class FrankEnergieSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Frank Energie sensor."""

    _attr_attribution = ATTRIBUTION
    _attr_icon = ICON
    #_attr_suggested_display_precision = DEFAULT_ROUND
    #_attr_device_class = SensorDeviceClass.MONETARY
    #_attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: FrankEnergieCoordinator,
        description: FrankEnergieEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description: FrankEnergieEntityDescription = description
        #if description.translation_key:
        #    self._attr_name = _(description.translation_key)
        self._attr_unique_id = f"{entry.unique_id}.{description.key}"
        # Do not set extra identifier for default service, backwards compatibility
        if description.service_name is SERVICE_NAME_PRICES:
            device_info_identifiers = {(DOMAIN, f"{entry.entry_id}")}
        else:
            device_info_identifiers = {(DOMAIN, f"{entry.entry_id}", description.service_name)}

        self._attr_device_info = DeviceInfo(
            identifiers=device_info_identifiers,
            name=f"{COMPONENT_TITLE} - {description.service_name}",
            manufacturer=COMPONENT_TITLE,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=API_CONF_URL,
            model=description.service_name,
            sw_version=VERSION,
        )

        # Set defaults or exceptions for non default sensors.
        #self._attr_device_class = description.device_class or self._attr_device_class
        #self._attr_state_class = description.state_class or self._attr_state_class
        #self._attr_suggested_display_precision = description.suggested_display_precision or self._attr_suggested_display_precision
        self._attr_icon = description.icon or self._attr_icon

        self._update_job = HassJob(self._handle_scheduled_update)
        self._unsub_update = None

        super().__init__(coordinator)

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        try:
            self._attr_native_value = self.entity_description.value_fn(
                self.coordinator.data
            )
        except (TypeError, IndexError, ValueError):
            # No data available
            self._attr_native_value = None

        # Cancel the currently scheduled event if there is any
        if self._unsub_update:
            self._unsub_update()
            self._unsub_update = None

        # Schedule the next update at exactly the next whole hour sharp
        next_update_time = utcnow().replace(minute=0, second=0) + timedelta(hours=1)
        self._unsub_update = event.async_track_point_in_utc_time(
            self.hass,
            self._update_job,
            next_update_time,
        )

    async def _handle_scheduled_update(self, _):
        """Handle a scheduled update."""
        # Only handle the scheduled update for entities which have a reference to hass,
        # which disabled sensors don't have.
        if self.hass is None:
            return

        self.async_schedule_update_ha_state(True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self.entity_description.attr_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None
