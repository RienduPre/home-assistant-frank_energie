"""Constants used in the Frank Energie integration."""
# const.py

import logging
from dataclasses import dataclass
from typing import Final

from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume
from python_frank_energie.models import (
    DeliverySite,
    Invoices,
    MarketPrices,
    MonthSummary,
    User,
)

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

# Attribution and data sources
ATTRIBUTION: Final[str] = "Data provided by Frank Energie"
DOMAIN: Final[str] = "frank_energie"
DATA_URL: Final[str] = "https://frank-graphql-prod.graphcdn.app/"
API_CONF_URL: Final[str] = "https://www.frankenergie.nl/goedkoop"
VERSION: Final[str] = "3.0.1"

# Default icon and component title
ICON: Final[str] = "mdi:currency-eur"
COMPONENT_TITLE: Final[str] = "Frank Energie"

# Unique ID for the component
UNIQUE_ID: Final[str] = "frank_energie"

# Config constants
CONF_COORDINATOR: Final[str] = "coordinator"
CONF_AUTH_TOKEN: Final[str] = "auth_token"
CONF_REFRESH_TOKEN: Final[str] = "refresh_token"
CONF_SITE: Final[str] = "site_reference"

# Attribute constants
ATTR_TIME: Final[str] = "from_time"

# Data and unit constants
DATA_ELECTRICITY: Final[str] = "electricity"
DATA_GAS: Final[str] = "gas"
DATA_MONTH_SUMMARY: Final[str] = "month_summary"
DATA_INVOICES: Final[str] = "invoices"
DATA_USER: Final[str] = "user"
DATA_DELIVERY_SITE: Final[str] = "delivery_site"
UNIT_ELECTRICITY: Final[str] = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"
UNIT_GAS: Final[str] = f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}"

# Services constants
SERVICE_NAME_PRICES: Final[str] = "Prices"
SERVICE_NAME_GAS_PRICES: Final[str] = "Gasprices"
SERVICE_NAME_ELEC_PRICES: Final[str] = "Electricityprices"
SERVICE_NAME_COSTS: Final[str] = "Costs"
SERVICE_NAME_USER: Final[str] = "User"
SERVICE_NAME_ACTIVE_DELIVERY_SITE: Final[str] = "Active_Delivery_Site"
SERVICE_NAME_USAGE: Final[str] = "Usage"

# Default round value for prices
DEFAULT_ROUND: Final[int] = 3

_LOGGER.info("Constants loaded for %s", DOMAIN)


@ dataclass
class DeviceResponseEntry:
    """Data class describing a single response entry."""
    electricity: MarketPrices
    gas: MarketPrices
    month_summary: MonthSummary | None
    invoices: Invoices | None
    user: User | None
    delivery_site: DeliverySite | None
