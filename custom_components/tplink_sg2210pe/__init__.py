import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .sensor import SG2210PEDataCoordinator

DOMAIN = "tplink_sg2210pe"
PLATFORMS = ["sensor", "switch", "button"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    host = entry.data["host"]
    username = entry.data["username"]
    password = entry.data["password"]

    coordinator = SG2210PEDataCoordinator(hass, host, username, password)
    await coordinator.async_config_entry_first_refresh()
    
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok