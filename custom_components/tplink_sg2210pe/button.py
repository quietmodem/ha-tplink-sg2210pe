import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .sensor import get_port_device_info

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tplink_sg2210pe"

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [SG2210PESystemRebootButton(coordinator)]
    data = coordinator.data or {}
    for port_id in range(1, data.get("poe_ports", 8) + 1):
        entities.append(SG2210PEPoEResetButton(coordinator, port_id))
        
    async_add_entities(entities)

class SG2210PESystemRebootButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._attr_name = "重启交换机"
        self._attr_icon = "mdi:restart"
        self._attr_unique_id = f"{coordinator.host}_system_reboot_btn"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name="TL-SG2210PE 主控交换机",
        )

    async def async_press(self) -> None:
        await self.coordinator.async_reboot_system()

class SG2210PEPoEResetButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, port_id):
        super().__init__(coordinator)
        self.port_id = port_id
        self._attr_name = "PoE 重新上电"
        self._attr_icon = "mdi:power-cycle"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_port_{port_id}_reset_btn"
        self._attr_device_info = get_port_device_info(coordinator.host, port_id, True)

    async def async_press(self) -> None:
        await self.coordinator.async_reset_poe_port(self.port_id)