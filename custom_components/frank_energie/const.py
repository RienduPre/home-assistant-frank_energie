"""
Constants used in the Frank Energie integration.
"""
# const.py

import logging
from dataclasses import dataclass
from typing import Final, Optional

from homeassistant.const import (CURRENCY_EURO, UnitOfEnergy,  # type: ignore
                                 UnitOfVolume)
from python_frank_energie.models import (DeliverySite, Invoices, MarketPrices,
                                         MonthSummary, User)

# --- Logger Setup ---
_LOGGER: logging.Logger = logging.getLogger(__name__)

# --- Domain Information ---
DOMAIN: Final[str] = "frank_energie"
VERSION: Final[str] = "2024.11.10"
ATTRIBUTION: Final[str] = "Data provided by Frank Energie"
UNIQUE_ID: Final[str] = "frank_energie"

# --- URLs ---
DATA_URL: Final[str] = "https://frank-graphql-prod.graphcdn.app/"
API_CONF_URL: Final[str] = "https://www.frankenergie.nl/goedkoop"

# --- Component Metadata ---
ICON: Final[str] = "mdi:currency-eur"
COMPONENT_TITLE: Final[str] = "Frank Energie"

# --- Configuration Constants ---
CONF_COORDINATOR: Final[str] = "coordinator"
CONF_AUTH_TOKEN: Final[str] = "auth_token"
CONF_REFRESH_TOKEN: Final[str] = "refresh_token"
CONF_SITE: Final[str] = "site_reference"

# --- Default values for some config constants ---
DEFAULT_REFRESH_INTERVAL: Final[int] = 3600

# --- Data Fields ---
DATA_ELECTRICITY: Final[str] = "electricity"
DATA_GAS: Final[str] = "gas"
DATA_MONTH_SUMMARY: Final[str] = "month_summary"
DATA_INVOICES: Final[str] = "invoices"
DATA_USER: Final[str] = "user"
DATA_DELIVERY_SITE: Final[str] = "delivery_site"

# --- Attribute Constants ---
ATTR_TIME: Final[str] = "from_time"

# --- Unit Constants ---
UNIT_ELECTRICITY: Final[str] = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"
UNIT_GAS: Final[str] = f"{CURRENCY_EURO}/{UnitOfVolume.CUBIC_METERS}"
UNIT_GAS_BE: Final[str] = f"{CURRENCY_EURO}/{UnitOfEnergy.KILO_WATT_HOUR}"

# --- Service Names ---
SERVICE_NAME_PRICES: Final[str] = "Prices"
SERVICE_NAME_GAS_PRICES: Final[str] = "Gasprices"
SERVICE_NAME_ELEC_PRICES: Final[str] = "Electricityprices"
SERVICE_NAME_COSTS: Final[str] = "Costs"
SERVICE_NAME_USER: Final[str] = "User"
SERVICE_NAME_ACTIVE_DELIVERY_SITE: Final[str] = "Active_Delivery_Site"
SERVICE_NAME_USAGE: Final[str] = "Usage"
SERVICE_NAME_ELEC_CONN: Final[str] = "Electricity connection"
SERVICE_NAME_GAS_CONN: Final[str] = "Gas connection"

# --- Display Constants ---
DEFAULT_ROUND: Final[int] = 3  # Default display round value for prices


# --- Device Response Data Class ---
@dataclass
class DeviceResponseEntry:
    """Data class describing a single response entry."""

    # Electricity prices and details
    electricity: MarketPrices

    # Gas prices and details
    gas: MarketPrices

    # Monthly summary (if available)
    month_summary: Optional[MonthSummary] = None

    # Invoice details (if available)
    invoices: Optional[Invoices] = None

    # User information (if available)
    user: Optional[User] = None

    # Delivery site details (if available)
    delivery_site: Optional[DeliverySite] = None


# Log loading of constants (move to init.py for better practice)
_LOGGER.info("Constants loaded for %s", DOMAIN)
