import logging
import asyncio
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory
from .sensor import get_port_device_info

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tplink_sg2210pe"

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    data = coordinator.data or {}
    max_p = data.get("max_ports", 10)
    poe_p = data.get("poe_ports", 8)

    entities = [
        SG2210PEPauseSwitch(coordinator)
    ]

    for port_id in range(1, max_p + 1):
        is_poe = (port_id <= poe_p)
        entities.append(SG2210PENetworkSwitch(coordinator, port_id))
        if is_poe:
            entities.append(SG2210PEPoESwitch(coordinator, port_id))
            entities.append(SG2210PEPoEResetButton(coordinator, port_id))

    async_add_entities(entities)

class SG2210PEPauseSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "暂停 HA 监控 (用于登录 Web)"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_pause_switch"
        self._attr_icon = "mdi:pause-circle"
        self._attr_entity_category = EntityCategory.CONFIG
        self._is_on = False
        self._auto_resume_task = None

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        self._is_on = True
        self.coordinator.pause_polling = True
        self.async_write_ha_state()
        _LOGGER.info("已暂停 TP-Link 交换机后台轮询（30分钟自动恢复）")

        if self._auto_resume_task and not self._auto_resume_task.done():
            self._auto_resume_task.cancel()

        self._auto_resume_task = asyncio.create_task(self._auto_resume_timer())

    async def async_turn_off(self, **kwargs):
        if self._auto_resume_task and not self._auto_resume_task.done():
            self._auto_resume_task.cancel()
        await self._do_resume()

    async def _auto_resume_timer(self):
        try:
            # 30分钟 = 1800 秒
            await asyncio.sleep(1800)
            if self._is_on:
                _LOGGER.info("30分钟暂停时间已到，自动恢复 TP-Link 交换机后台监控")
                await self._do_resume()
        except asyncio.CancelledError:
            pass

    async def _do_resume(self):
        self._is_on = False
        self.coordinator.pause_polling = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

class SG2210PENetworkSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, port_id):
        super().__init__(coordinator)
        self.port_id = port_id
        self._attr_name = f"端口 {port_id} 网络状态"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_net_switch_{port_id}"
        self._attr_icon = "mdi:ethernet"

    @property
    def device_info(self):
        is_poe = self.port_id <= self.coordinator.data.get("poe_ports", 8)
        return get_port_device_info(self.coordinator.host, self.port_id, is_poe)

    @property
    def is_on(self):
        port_data = self.coordinator.data.get("ports", {}).get(self.port_id, {})
        return port_data.get("network_enabled", True)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_net_port(self.port_id, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_net_port(self.port_id, False)

class SG2210PEPoESwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, port_id):
        super().__init__(coordinator)
        self.port_id = port_id
        self._attr_name = f"端口 {port_id} PoE 供电"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_poe_switch_{port_id}"
        self._attr_icon = "mdi:flash"

    @property
    def device_info(self):
        return get_port_device_info(self.coordinator.host, self.port_id, True)

    @property
    def is_on(self):
        port_data = self.coordinator.data.get("ports", {}).get(self.port_id, {})
        return port_data.get("pstate_raw") == "2"

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_poe_port(self.port_id, 2)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_poe_port(self.port_id, 1)

class SG2210PEPoEResetButton(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, port_id):
        super().__init__(coordinator)
        self.port_id = port_id
        self._attr_name = f"端口 {port_id} PoE 重新上电"
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_poe_reset_{port_id}"
        self._attr_icon = "mdi:power-cycle"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self):
        return get_port_device_info(self.coordinator.host, self.port_id, True)

    @property
    def is_on(self):
        return False

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_reset_poe_port(self.port_id)

    async def async_turn_off(self, **kwargs):
        pass
