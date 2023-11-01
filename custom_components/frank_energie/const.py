"""Constants used in the Frank Energie integration."""
# const.py

import logging
from typing import Final

from homeassistant.const import CURRENCY_EURO, UnitOfEnergy, UnitOfVolume

_LOGGER: Final[logging.Logger] = logging.getLogger(__package__)

# Attribution and data sources
ATTRIBUTION: Final[str] = "Data provided by Frank Energie"
DOMAIN: Final[str] = "frank_energie"
DATA_URL: Final[str] = "https://frank-graphql-prod.graphcdn.app/"
API_CONF_URL: Final[str] = "https://www.frankenergie.nl/goedkoop"
VERSION: Final[str] = "2.5.1"

# Default icon and component title
ICON: Final[str] = "mdi:currency-eur"
COMPONENT_TITLE: Final[str] = "Frank Energie"

# Unique ID for the component
UNIQUE_ID: Final[str] = "frank_energie"

# Config constants
CONF_COORDINATOR: Final[str] = "coordinator"

# Attribute constants
ATTR_TIME: Final[str] = "from_time"

# Electricity and gas constants
DATA_ELECTRICITY: Final[str] = "electricity"
DATA_GAS: Final[str] = "gas"
DATA_MONTH_SUMMARY: Final[str] = "month_summary"
DATA_INVOICES: Final[str] = "invoices"
DATA_USER: Final[str] = "user"
UNIT_ELECTRICITY: Final[str] = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"
UNIT_GAS: Final[str] = f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}"

SERVICE_NAME_PRICES: Final[str] = "Prices"
SERVICE_NAME_COSTS: Final[str] = "Costs"
SERVICE_NAME_USER: Final[str] = "User"

# Default round value for prices
DEFAULT_ROUND: Final[int] = 3

_LOGGER.info("Constants loaded for %s", DOMAIN)
