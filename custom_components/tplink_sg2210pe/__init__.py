import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

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

    # HA 2026.8+ requires via_device_id (the parent device's registry id)
    # instead of the deprecated via_device identifier tuple. Register the
    # main switch device up front and remember its registry id so the port
    # devices can link to it; the main device's own entities keep using the
    # same identifiers and land on this very entry.
    parent_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, host)},
        manufacturer="TP-Link",
        model="TL-SG2210PE",
        name="TL-SG2210PE 主控交换机",
    )
    coordinator.parent_device_id = parent_device.id
    
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok