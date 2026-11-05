import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .sensor import get_port_device_info

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tplink_sg2210pe"

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    
    entities.append(SG2210PEPauseSwitch(coordinator))
    
    data = coordinator.data or {}
    for port_id in range(1, data.get("max_ports", 10) + 1):
        entities.append(SG2210PENetworkSwitch(coordinator, port_id))
    for port_id in range(1, data.get("poe_ports", 8) + 1):
        entities.append(SG2210PEPoESwitch(coordinator, port_id))
    
    async_add_entities(entities)

class SG2210PEPauseSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "暂停 HA 监控 (用于登录 Web)"
        self._attr_icon = "mdi:pause-circle"
        self._attr_unique_id = f"{coordinator.host}_pause_polling"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.host)},
            name="TL-SG2210PE 主控交换机",
        )

    @property
    def is_on(self) -> bool:
        return getattr(self.coordinator, "pause_polling", False)

    async def async_turn_on(self, **kwargs):
        self.coordinator.pause_polling = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self.coordinator.pause_polling = False
        await self.coordinator.async_request_refresh()

class SG2210PENetworkSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, port_id):
        super().__init__(coordinator)
        self.port_id = port_id
        self._attr_name = "网口数据开关"
        self._attr_icon = "mdi:ethernet"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_port_{port_id}_network_switch"
        self._attr_device_info = get_port_device_info(coordinator.host, port_id, port_id <= (coordinator.data or {}).get("poe_ports", 8), coordinator.parent_device_id)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("ports", {}).get(self.port_id, {}).get("network_enabled", True)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_net_port(self.port_id, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_net_port(self.port_id, False)

class SG2210PEPoESwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, port_id):
        super().__init__(coordinator)
        self.port_id = port_id
        self._attr_name = "PoE 供电开关"
        self._attr_icon = "mdi:power-plug"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_port_{port_id}_poe_switch"
        self._attr_device_info = get_port_device_info(coordinator.host, port_id, True, coordinator.parent_device_id)

    @property
    def is_on(self) -> bool:
        return str(self.coordinator.data.get("ports", {}).get(self.port_id, {}).get("pstate_raw")) == "2"

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_poe_port(self.port_id, "2")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_poe_port(self.port_id, "1")
