"""The Frank Energie component."""

from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import Entity
from python_frank_energie import FrankEnergie

from .const import _LOGGER, CONF_COORDINATOR, DOMAIN
from .coordinator import FrankEnergieCoordinator

# PLATFORMS = [Platform.SENSOR, "frank_energie_diagnostic_sensor"]
PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Frank Energie component from a config entry."""
    component = FrankEnergieComponent(hass, entry)
    return await component.setup()
    # return True


async def async_setup_platform(hass: HomeAssistant, config: dict[str, Any], async_add_entities, discovery_info=None):
    """Set up the Frank Energie sensor platform."""
    coordinator = hass.data[DOMAIN][CONF_COORDINATOR]
    api = coordinator.api
    sensor = FrankEnergieDiagnosticSensor(api)
    async_add_entities([sensor])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    _LOGGER.debug("Unloading entry...")
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class FrankEnergieComponent:
    """Class representing the Frank Energie component."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Frank Energie component."""
        self.hass = hass
        self.entry = entry

    async def setup(self) -> bool:
        """Set up the Frank Energie component from a config entry."""

        # For backwards compatibility, set unique ID
        self._update_unique_id()
        api = self._create_frank_energie_api()
        coordinator = self._create_frank_energie_coordinator(api)
        # await coordinator.async_config_entry_first_refresh()
        await self._async_config_entry_first_refresh(coordinator)
        self._save_coordinator_to_hass_data(coordinator)
        # await self.hass.config_entries.async_forward_entry_setups(self.entry, PLATFORMS)
        await self._async_forward_entry_setups()
        return True

    async def _async_config_entry_first_refresh(self, coordinator: FrankEnergieCoordinator) -> None:
        """Perform the initial refresh for the coordinator."""
        await coordinator.async_config_entry_first_refresh()

    async def _async_forward_entry_setups(self) -> None:
        """Forward entry setups to appropriate platforms."""
        await self.hass.config_entries.async_forward_entry_setups(self.entry, PLATFORMS)

    def _update_unique_id(self) -> None:
        """Update the unique ID of the config entry."""
        if self.entry.unique_id is None or self.entry.unique_id == "frank_energie_component":
            self.hass.config_entries.async_update_entry(self.entry, unique_id="frank_energie")

    def _create_frank_energie_api(self) -> FrankEnergie:
        """Create the Frank Energie API instance."""
        return FrankEnergie(
            clientsession=async_get_clientsession(self.hass),
            auth_token=self.entry.data.get(CONF_ACCESS_TOKEN),
            refresh_token=self.entry.data.get(CONF_TOKEN),
        )

    def _create_frank_energie_coordinator(self, api: FrankEnergie) -> FrankEnergieCoordinator:
        """Create the Frank Energie Coordinator instance."""
        return FrankEnergieCoordinator(self.hass, self.entry, api)

    def _save_coordinator_to_hass_data(self, coordinator: FrankEnergieCoordinator) -> None:
        """Save the coordinator to the Home Assistant data."""
        # self.hass.data.setdefault(DOMAIN, {})
        # self.hass.data[DOMAIN][self.entry.entry_id] = {CONF_COORDINATOR: coordinator}
        hass_data = self.hass.data.setdefault(DOMAIN, {})
        hass_data[self.entry.entry_id] = {CONF_COORDINATOR: coordinator}

    def _remove_entry_from_hass_data(self) -> None:
        """Remove the entry from the Home Assistant data."""
        self.hass.data[DOMAIN].pop(self.entry.entry_id)


class FrankEnergieDiagnosticSensor(Entity):
    """Class representing the Frank Energie diagnostic sensor."""

    def __init__(self, frank_energie: FrankEnergie) -> None:
        """Initialize the sensor."""
        self._frank_energie = frank_energie
        self._state: Optional[str] = None

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "frank_energie_diagnostic_sensor"

    @property
    def state(self) -> Optional[str]:
        """Return the sensor state."""
        return self._state

    @property
    def device_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            # Add additional attributes if needed
        }

    async def async_update(self) -> None:
        """Update the sensor state."""
        # Implement the logic to update the sensor state
        # You can use the FrankEnergie API client instance (self._frank_energie)
        # to fetch diagnostic data and update the sensor state accordingly
        try:
            self._state = await self._frank_energie.get_diagnostic_data()
        except Exception as e:
            # Handle specific exceptions and raise more descriptive ones if necessary
            raise ValueError(f"Failed to update FrankEnergieDiagnosticSensor: {str(e)}")