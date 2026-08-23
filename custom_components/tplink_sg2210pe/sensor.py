import logging
import urllib.parse
import re
import asyncio
from datetime import timedelta
import aiohttp

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfPower, UnitOfDataRate, UnitOfElectricCurrent, UnitOfElectricPotential, EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)
DOMAIN = "tplink_sg2210pe"

POE_STATUS_MAP = {
    0: "未供电", 2: "供电", 3: "过载", 4: "短路", 
    5: "非标准PD", 6: "电压过高", 7: "电压过低", 8: "硬件错误", 
    9: "温度过高", 10: "下一端口拒载", 11: "优先级拒载", 12: "无法识别"
}

def tp_encrypt(password: str) -> str:
    b = "RDpbLfCPsJZ7fiv"
    a = "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4rBL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro510qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZLEal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW"
    e, c, j = len(password), len(b), len(a)
    result = ""
    for g in range(max(e, c)):
        l = ord(password[g]) if g < e else 187
        i = ord(b[g]) if g < c else 187
        result += a[(l ^ i) % j]
    return result

def get_port_device_info(host: str, port_id: int, is_poe: bool) -> DeviceInfo:
    if is_poe:
        suffix = ""
        model = "PoE Port"
    elif port_id == 10:
        suffix = " (光口)"
        model = "SFP Port"
    else:
        suffix = " (数据口)"
        model = "RJ45 Port"

    return DeviceInfo(
        identifiers={(DOMAIN, f"{host}_port_{port_id}")},
        name=f"TL-SG2210PE 端口 {port_id}{suffix}",
        manufacturer="TP-Link",
        model=model,
        via_device=(DOMAIN, host),
    )

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    data = coordinator.data or {}
    max_p = data.get("max_ports", 10)
    poe_p = data.get("poe_ports", 8)

    entities = [
        SG2210PESensor(coordinator, "used_poe_power", "PoE 已用功耗", UnitOfPower.WATT, SensorDeviceClass.POWER),
        SG2210PESensor(coordinator, "remain_poe_power", "PoE 剩余功耗", UnitOfPower.WATT, SensorDeviceClass.POWER),
        SG2210PESensor(coordinator, "total_poe_power", "PoE 总预算", UnitOfPower.WATT, SensorDeviceClass.POWER),
        SG2210PESensor(coordinator, "uptime", "运行时间", None, None),
    ]

    for port_id in range(1, max_p + 1):
        if port_id <= poe_p:
            entities.append(SG2210PEPortSensor(coordinator, port_id, "PoE 供电状态", "power_status_str", None, None))
            entities.append(SG2210PEPortSensor(coordinator, port_id, "PoE 功率", "power", UnitOfPower.WATT, SensorDeviceClass.POWER))
            entities.append(SG2210PEPortSensor(coordinator, port_id, "PoE 电压", "voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE))
            entities.append(SG2210PEPortSensor(coordinator, port_id, "PoE 电流", "current", UnitOfElectricCurrent.MILLIAMPERE, SensorDeviceClass.CURRENT))
            entities.append(SG2210PEPortSensor(coordinator, port_id, "PoE PD Class", "pdclass", None, None))
            
        entities.append(SG2210PEPortSensor(coordinator, port_id, "网口 发送速率", "tx_rate", UnitOfDataRate.MEGABITS_PER_SECOND, SensorDeviceClass.DATA_RATE))
        entities.append(SG2210PEPortSensor(coordinator, port_id, "网口 接收速率", "rx_rate", UnitOfDataRate.MEGABITS_PER_SECOND, SensorDeviceClass.DATA_RATE))

    async_add_entities(entities)

class SG2210PEDataCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host, username, password):
        super().__init__(hass, _LOGGER, name="tplink_sg2210pe", update_interval=timedelta(seconds=15))
        self.host = host
        self.username = username
        self.password = password
        self.session = None
        self.token = ""
        self.cookie_session = ""
        self.pause_polling = False
        self.api_lock = asyncio.Lock()
        self.data = {"ports": {}, "max_ports": 10, "poe_ports": 8, "hw_ver": "Unknown", "fw_ver": "Unknown", 
                     "total_poe_power": 120.0, "used_poe_power": 0.0, "remain_poe_power": 120.0, "uptime": "未知"}

    def _extract_token(self, text):
        m = re.search(r"(?:token|g_tid)\s*[:=]\s*['\"]?(\d+)['\"]?", text, re.IGNORECASE)
        if m:
            self.token = m.group(1)

    async def _safe_request(self, method, uri, referer, raw_data_str=None, params=None):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())

        url = f"http://{self.host}/{uri}"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": f"http://{self.host}/{referer}",
            "Connection": "keep-alive"
        }

        if self.cookie_session:
            headers["Cookie"] = f"SessionID={self.cookie_session}"

        data_bytes = None
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Origin"] = f"http://{self.host}"
            if raw_data_str:
                data_bytes = raw_data_str.encode("ascii")
                headers["Content-Length"] = str(len(data_bytes))

        if params:
            url += "?" + urllib.parse.urlencode(params)

        try:
            async with self.session.request(method, url, headers=headers, data=data_bytes, timeout=10) as resp:
                text = await resp.text(errors='ignore')
                self._extract_token(text)
                if 'location.href="/"' in text or 'location.href="logon.cgi"' in text:
                    raise Exception("Session expired")
                return text
        except aiohttp.ServerDisconnectedError:
            return ""
        except Exception as e:
            raise e

    async def _login(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar())

        payload = {
            "username": self.username,
            "password": tp_encrypt(self.password),
            "isle": "false",
            "logon": "登录"
        }
        url = f"http://{self.host}/logon.cgi"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"http://{self.host}/"
        }
        
        raw_data = urllib.parse.urlencode(payload, encoding="gbk")

        try:
            async with self.session.post(url, headers=headers, data=raw_data.encode("ascii"), timeout=10) as resp:
                for key, value in resp.headers.items():
                    if key.lower() == "set-cookie":
                        match = re.search(r"SessionID=([^;]+)", value, re.IGNORECASE)
                        if match:
                            self.cookie_session = match.group(1)
        except Exception:
            pass

        try:
            await self._safe_request("GET", "", "")
            await self._safe_request("GET", "MainRpm.htm", "Menu.htm")
        except Exception:
            pass

    async def _async_update_data(self):
        if self.pause_polling:
            return self.data
            
        async with self.api_lock:
            try:
                main_html = await self._safe_request("GET", "MainRpm.htm", "Menu.htm")
                if "logon.cgi" in main_html or not self.token:
                    await self._login()
                    main_html = await self._safe_request("GET", "MainRpm.htm", "Menu.htm")
                poe_html = await self._safe_request("GET", "PoeConfigRpm.htm", "MainRpm.htm")
                sys_html = await self._safe_request("GET", "SystemInfoRpm.htm", "Menu.htm")
                
                return self._parse_html(main_html, poe_html, sys_html)
            except Exception:
                return self.data

    async def async_set_net_port(self, port_id, enable):
        if port_id in self.data.get("ports", {}):
            self.data["ports"][port_id]["network_enabled"] = enable
            self.async_set_updated_data(self.data)

        async with self.api_lock:
            await self._login()
            state_val = "1" if enable else "0"
            params = {
                "token": self.token,
                f"port_sel_{port_id}": state_val
            }
            try:
                await self._safe_request("GET", "main_info_port_status_set.cgi", "MainRpm.htm", params=params)
            except Exception as e:
                _LOGGER.error(f"网口控制失败: {e}")
                if port_id in self.data.get("ports", {}):
                    self.data["ports"][port_id]["network_enabled"] = not enable
                    self.async_set_updated_data(self.data)
                    
        await asyncio.sleep(2.0)
        await self.async_request_refresh()

    async def async_set_poe_port(self, port_id, pstate):
        if port_id in self.data.get("ports", {}):
            self.data["ports"][port_id]["pstate_raw"] = str(pstate)
            self.async_set_updated_data(self.data)

        async with self.api_lock:
            await self._login()
            port_data = self.data["ports"].get(port_id, {})
            prio = port_data.get("priority_raw", "7")
            lim = port_data.get("limit_mode_raw", "7")
            
            payload = {
                "name_pstate": pstate,
                "name_ppriority": prio,
                "name_ppowerlimit": lim,
                f"sel_{port_id}": "1",
                "applay": "应用",
                "token": self.token
            }
            if str(lim) == "6":
                payload["name_ppowerlimit2"] = port_data.get("limit_val_raw", "300")

            raw_data_str = urllib.parse.urlencode(payload, encoding="gbk")
            try:
                await self._safe_request("POST", "poe_port_config.cgi", "PoeConfigRpm.htm", raw_data_str=raw_data_str)
            except Exception as e:
                _LOGGER.error(f"PoE控制失败: {e}")
                
        await asyncio.sleep(2.0)
        await self.async_request_refresh()

    async def async_reset_poe_port(self, port_id):
        async with self.api_lock:
            await self._login()
            port_data = self.data["ports"].get(port_id, {})
            prio = port_data.get("priority_raw", "7")
            lim = port_data.get("limit_mode_raw", "7")
            
            payload = {
                "name_pstate": "2",
                "name_ppriority": prio,
                "name_ppowerlimit": lim,
                f"sel_{port_id}": "1",
                f"reset_{port_id}": "重新上电",
                "applay": "应用",
                "token": self.token
            }
            if str(lim) == "6":
                payload["name_ppowerlimit2"] = port_data.get("limit_val_raw", "300")

            raw_data_str = urllib.parse.urlencode(payload, encoding="gbk")
            try:
                await self._safe_request("POST", "poe_port_config.cgi", "PoeConfigRpm.htm", raw_data_str=raw_data_str)
            except Exception as e:
                _LOGGER.error(f"PoE重新上电失败: {e}")
                
        await asyncio.sleep(2.0)
        await self.async_request_refresh()

    async def async_reboot_system(self):
        async with self.api_lock:
            await self._login()
            payload = {"reboot_op": "reboot", "save_op": "true", "token": self.token}
            try:
                raw_data_str = urllib.parse.urlencode(payload, encoding="gbk")
                await self._safe_request("POST", "reboot.cgi", "SystemRebootRpm.htm", raw_data_str=raw_data_str)
            except Exception:
                pass

    def _parse_html(self, main_html, poe_html, sys_html=""):
        result = self.data.copy()
        try:
            combine_html = sys_html + main_html
            hw_match = re.search(r"hardwareStr:\s*\[\"(.*?)\"\]", combine_html)
            fw_match = re.search(r"firmwareStr:\s*\[\"(.*?)\"\]", combine_html)
            if hw_match: result["hw_ver"] = hw_match.group(1)
            if fw_match: result["fw_ver"] = fw_match.group(1)

            mp_match = re.search(r"max_port_num\s*=\s*(\d+)", main_html)
            pp_match = re.search(r"poe_port_num\s*=\s*(\d+)", poe_html)
            if mp_match: result["max_ports"] = int(mp_match.group(1))
            if pp_match: result["poe_ports"] = int(pp_match.group(1))

            time_match = re.search(r"workTime\s*:\s*\[\"(.*?)\"\]", main_html)
            if time_match:
                t_str = time_match.group(1)
                d_match = re.search(r"(\d+)\s*day", t_str)
                h_match = re.search(r"(\d+)\s*hour", t_str)
                days = int(d_match.group(1)) if d_match else 0
                hours = int(h_match.group(1)) if h_match else 0
                result["uptime"] = f"{days}天 {hours}小时" if days > 0 else f"{hours}小时"

            sys_match = re.search(r"globalConfig\s*=\s*\{([^}]+)\}", poe_html, re.DOTALL)
            if sys_match:
                sys_data = sys_match.group(1)
                lim = re.search(r"system_power_limit\s*:\s*(\d+)", sys_data)
                con = re.search(r"system_power_consumption\s*:\s*(\d+)", sys_data)
                rem = re.search(r"system_power_remain\s*:\s*(\d+)", sys_data)
                if lim: result["total_poe_power"] = float(lim.group(1)) / 10.0
                if con: result["used_poe_power"] = float(con.group(1)) / 10.0
                if rem: result["remain_poe_power"] = float(rem.group(1)) / 10.0

            net_states, rx_rates, tx_rates = [], [], []
            info_match = re.search(r"port_info\s*=\s*\{([^}]+)\}", main_html, re.DOTALL)
            if info_match:
                i_content = info_match.group(1)
                st_m = re.search(r"state\s*:\s*\[(.*?)\]", i_content, re.DOTALL)
                rx_m = re.search(r"rx_rate\s*:\s*\[(.*?)\]", i_content, re.DOTALL)
                tx_m = re.search(r"tx_rate\s*:\s*\[(.*?)\]", i_content, re.DOTALL)
                if st_m: net_states = [int(x.strip()) for x in st_m.group(1).split(",") if x.strip()]
                if rx_m: rx_rates = [float(x.strip())/1000.0 for x in rx_m.group(1).split(",") if x.strip()]
                if tx_m: tx_rates = [float(x.strip())/1000.0 for x in tx_m.group(1).split(",") if x.strip()]

            p_states, p_prios, p_limits, p_powers, p_currs, p_volts, p_class, p_status = [], [], [], [], [], [], [], []
            port_match = re.search(r"portConfig\s*=\s*\{([^}]+)\}", poe_html, re.DOTALL)
            if port_match:
                p_content = port_match.group(1)
                st_p = re.search(r"state\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                pr_p = re.search(r"priority\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                pl_p = re.search(r"powerlimit\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                pw_p = re.search(r"power\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                cu_p = re.search(r"current\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                vo_p = re.search(r"voltage\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                cl_p = re.search(r"pdclass\s*:\s*\[(.*?)\]", p_content, re.DOTALL)
                ps_p = re.search(r"powerstatus\s*:\s*\[(.*?)\]", p_content, re.DOTALL)

                if st_p: p_states = [int(x.strip()) for x in st_p.group(1).split(",") if x.strip()]
                if pr_p: p_prios = [int(x.strip()) for x in pr_p.group(1).split(",") if x.strip()]
                if pl_p: p_limits = [int(x.strip()) for x in pl_p.group(1).split(",") if x.strip()]
                if pw_p: p_powers = [float(x.strip())/10.0 for x in pw_p.group(1).split(",") if x.strip()]
                if cu_p: p_currs = [int(x.strip()) for x in cu_p.group(1).split(",") if x.strip()]
                if vo_p: p_volts = [float(x.strip())/10.0 for x in vo_p.group(1).split(",") if x.strip()]
                if cl_p: p_class = [int(x.strip()) for x in cl_p.group(1).split(",") if x.strip()]
                if ps_p: p_status = [int(x.strip()) for x in ps_p.group(1).split(",") if x.strip()]

            for i in range(1, result["max_ports"] + 1):
                idx = i - 1
                result["ports"][i] = {
                    "network_enabled": net_states[idx] == 1 if idx < len(net_states) else True,
                    "rx_rate": rx_rates[idx] if idx < len(rx_rates) else 0.0,
                    "tx_rate": tx_rates[idx] if idx < len(tx_rates) else 0.0,
                }
                if i <= result["poe_ports"]:
                    pstate_val = (p_states[idx] + 1) if idx < len(p_states) else 2
                    result["ports"][i].update({
                        "power_status_str": POE_STATUS_MAP.get(p_status[idx], "未知") if idx < len(p_status) else "未知",
                        "pstate_raw": str(pstate_val), 
                        "priority_raw": str(p_prios[idx]) if idx < len(p_prios) else "7",
                        "limit_mode_raw": str(p_limits[idx]) if idx < len(p_limits) else "7",
                        "limit_val_raw": str(p_limits[idx]) if idx < len(p_limits) else "300",
                        "power": p_powers[idx] if idx < len(p_powers) else 0.0,
                        "current": p_currs[idx] if idx < len(p_currs) else 0.0,
                        "voltage": p_volts[idx] if idx < len(p_volts) else 0.0,
                        "pdclass": p_class[idx] if idx < len(p_class) else 0,
                    })
        except Exception:
            pass
        return result

class SG2210PESensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key, name, unit, device_class):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if device_class:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key == "uptime":
            self._attr_icon = "mdi:clock-outline"
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_{key}"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.host)},
            name="TL-SG2210PE 主控交换机",
            manufacturer="TP-Link",
            model=self.coordinator.data.get("hw_ver", "TL-SG2210PE"),
            sw_version=self.coordinator.data.get("fw_ver", "Unknown")
        )

    @property
    def native_value(self):
        val = self.coordinator.data.get(self._key, 0.0 if self._attr_device_class else "未知")
        if isinstance(val, float):
            return round(val, 2)
        return val

class SG2210PEPortSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, port_id, name, key, unit, device_class):
        super().__init__(coordinator)
        self.port_id = port_id
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if device_class:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = f"{coordinator.host}_sg2210pe_port_{port_id}_{key}"
        
        is_sfp = (self.port_id == 10)
        if key in ["tx_rate", "rx_rate"]:
            self._attr_icon = "mdi:lan" if not is_sfp else "mdi:expansion-port"

    @property
    def device_info(self):
        is_poe = self.port_id <= self.coordinator.data.get("poe_ports", 8)
        return get_port_device_info(self.coordinator.host, self.port_id, is_poe)

    @property
    def native_value(self):
        val = self.coordinator.data.get("ports", {}).get(self.port_id, {}).get(self._key, 0.0 if self._attr_device_class else "未知")
        if isinstance(val, float):
            return round(val, 2)
        return val