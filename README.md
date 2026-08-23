# Home Assistant Integration: TP-Link TL-SG2210PE

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

这是一个用于 Home Assistant 的自定义集成，专门为 TP-Link TL-SG2210PE 网管型 PoE 交换机开发。通过抓包逆向分析其底层 CGI 接口，实现了对交换机数据面和供电面的全方位接入与控制。

## 简介
由于 TP-Link 早期 Web 管理界面采用单线程 CGI 且强制“单一管理员”机制，极易导致并发控制冲突和 UI 状态回弹。本集成在底层重写了通信逻辑，采用“用完即毁（Ephemeral Session）”模式和全局通信锁，并解决了 GBK 编码引发的底层乱码拒接问题，实现了稳定流畅的 HA 接入体验。

## ✨ 主要功能

*   **数据口控制**：支持开启/关闭指定端口的网络数据传输。
*   **PoE 供电控制**：支持开启/关闭指定端口的 PoE 供电，并支持一键“重新上电（Reset）”。
*   **实时速率监控**：监控每个端口的实时发送（Tx）和接收（Rx）速率，区分 RJ45 数据口与 SFP 光口图标。
*   **PoE 状态监控**：实时读取单端口的 PoE 运行功率 (W)、电流 (mA)、电压 (V) 及 PD Class。
*   **全局状态面板**：监控交换机系统运行时间，以及 PoE 总预算、已用功率和剩余功率。
*   **设备级联展示**：自动识别端口类型（RJ45/SFP/PoE），并在 HA 设备面板中分层级展示。

## 📦 安装方法 (通过 HACS)

1. 打开 Home Assistant 的 **HACS** 面板。
2. 点击右上角的三个点 `⋮`，选择 **自定义存储库 (Custom repositories)**。
3. 在“存储库”中输入本项目的 GitHub 链接：`https://github.com/hjj
4. 0529/ha-tplink-sg2210pe`
5. “类别”选择 **集成 (Integration)**，点击添加。
6. 在 HACS 中搜索 `TL-SG2210PE`，点击下载并重启 Home Assistant。

## ⚙️ 配置方法

1. 重启 HA 后，进入 **配置** -> **设备与服务**。
2. 点击右下角 **添加集成**，搜索 `TP-Link TL-SG2210PE`。
3. 输入交换机的管理 IP 地址、Web 登录用户名和密码即可完成添加。

> **⚠️ 重要提示**：
> TP-Link 该系列交换机强制执行“唯一管理员”机制。当 Home Assistant 正在后台轮询或下发控制指令时，**请勿在电脑/手机浏览器中长时间停留或刷新交换机的 Web 管理页面**，否则会互相挤占 Session 导致控制指令失效；如果需要登录WEB页面，建议先在集成里面打开暂停HA监控开关。
