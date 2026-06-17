# CarrotPilot-C3-ESCC

这是一个面向个人 C3 中国克隆版和 Kia Seltos 2023 纯 CAN 车辆的 CarrotPilot 整合分支。

当前状态：

- 底座：`ajouatom/openpilot:c3-wip`
- 主车：Kia Seltos 2023，初期复用 Seltos 2021 配置
- 硬件：C3 中国克隆版，不是 C3X
- ESCC：已接入最小支持，默认关闭，必须手动开启 `EnableEscc`
- 离线模式：`AlwaysOffline` 默认开启，用于 ACC/CAN 供电、无法在线注册的设备
- Auto-Tuner：已接入学习和手动确认闭环，默认关闭，不自动应用
- CP搭子 / Navipilot：核心 CarrotMan / CPlink 协议静态兼容，已增加 C3 侧 APP 端点 live check，手机 APP 实测未完成
- 模型选择器：已跟踪参考线并增加源码审计，默认主线未启用模型下载或 modeld 切换
- AmapNavi / 自动超车 / DEC：已跟踪 fishop 和 Navipilot APP 来源；只读 AmapNavi 状态桥默认关闭，完整 AmapNavi/自动超车/DEC 未启用

当前可参考 tag：

- 静态检查：`carrotpilot-c3-escc-20260618-static24`
- 受控上车测试：`carrotpilot-c3-escc-20260618-test16`
- `static` / `test` 都不代表实车验证完成或稳定版
- 还没有 `stable` tag
- 机器可检查的安装目标见 [INSTALL_TARGETS.json](docs/personal/INSTALL_TARGETS.json)，当前日常稳定安装目标为空

自动检查：

- GitHub Actions 的 `Personal Smoke` 会在个人分支推送和手动触发时运行。
- 它覆盖 Seltos 2023 纯 CAN 复用策略、ESCC、Always Offline、CP搭子核心协议、Auto-Tuner 默认安全状态、上游更新计划工具、模型选择器、只读 AmapNavi 状态桥及其可选实机采样证据、AmapNavi/自动超车来源审计、功能边界守卫、证据就绪度报告和中文设置说明。
- `Upstream Watch` 每周和手动触发时比较 ajouatom、jixiexiaoge/openpilot、jixiexiaoge/navipilot、fishop 的最新分支和 [UPSTREAM_BASELINES.json](docs/personal/UPSTREAM_BASELINES.json)；变红通常表示有新上游提交需要审查。
- 本地更新前可先运行 `python3 scripts/personal/upstream_update_plan.py --fetch`，它会给出 tracking 分支快进计划、高风险目录和后续门禁命令，默认不修改代码。
- Actions 通过不代表实车验证通过。

安装、更新或上车前先看：

- [安装和回滚说明](docs/personal/INSTALL_AND_ROLLBACK.md)
- [从旧版本迁移安全参数](docs/personal/CONFIG_MIGRATION.md)
- [安装目标清单](docs/personal/INSTALL_TARGETS.json)
- [设备端快照采集](docs/personal/DEVICE_SNAPSHOT.md)
- [上车测试记录模板](docs/personal/ROAD_TEST_LOG_TEMPLATE.md)
- [以后更新检查单](docs/personal/UPDATE_CHECKLIST.md)
- [当前代码改动记录](docs/personal/CODE_CHANGES.md)
- [来源和署名](docs/personal/SOURCES_AND_CREDITS.md)

重要边界：

- 不要把日常开发分支当长期安装目标。
- `static` tag 不能替代实车验证。
- GitHub Actions / smoke check 不能替代上车静态检查和低速路测。
- ESCC 需要确认车上能稳定看到 0x2AB，并确认 lead、AEB/FCW、SCC 状态正常。
- Seltos 2023 是纯 CAN，默认不要开启 CANFD/HDA2 相关路径。
- 任何异常加减速、SCC/AEB 报错或车型路径错误，都应立即关闭 ESCC 并回滚。

来源和署名：

- 基于 ajouatom 维护的 CarrotPilot / CarPad 当前 C3 主源分支。
- ESCC 及部分 Hyundai/Kia 国内硬件支持参考 fishop / 飞扬（码上飞扬，名称待确认）的实现。
- CP搭子、Navipilot、在线调参、7000 Web 等功能参考机械小哥 / JixieXiaoGe 的实现，包括 `jixiexiaoge/openpilot` 和 `jixiexiaoge/navipilot`。
- `dhvms/carrotpilot` 当前只作为旧 CarrotPilot 说明和历史实现参考，不作为主底座。
- 所有上游许可证、免责声明和贡献署名均保留。

下面保留上游 CarrotPilot / openpilot 原始说明。上游文档中的 `openpilot.comma.ai` 是官方 openpilot 安装入口，不是本个人分支的安装目标。

## ⚠️ 법적 안내 / Legal Notice

🚫 대한민국 자동차관리법 개정안에 따라, 본 소프트웨어를 실제 차량에 장착하거나 주행에 사용하는 것은 법률에 위배될 수 있습니다.  
이 저장소에 있는 모든 소프트웨어는 **연구, 실험, 시뮬레이션 목적**으로만 제공됩니다.  
개발자는 본 소프트웨어의 실제 사용으로 인해 발생하는 **모든 법적 책임을 지지 않습니다.**

In accordance with the amended **Korean Motor Vehicle Management Act** (effective August 14, 2025),  
**modifying or installing software that affects the safe operation of a vehicle** is prohibited.

This software is provided **for research and educational use only**.  
The developer does **not take any responsibility** for real-world installation or usage.

**Carrotpilot에서 사용하는 차량(현대,기아)에 따라 Harness가 다릅니다..**
- CAN통신차량: Comma 정품 Harness, Camera에 연결
- CANFD-일반차량: Comma정품 Harness, Camera에 연결
- CANFD-HDA2(ADAS Module 장착)차량: 사제 Harness, ADAS Module에 연결
- 모든차량이 지원되는것이 아니니 반드시 확인바랍니다.
  
**In CarrotPilot, the harness used varies depending on the vehicle(HKG):**
* **CAN vehicles** Use the official Comma harness, connected to the camera.
* **CAN FD (standard) vehicles** Use the official Comma harness, connected to the camera.
* **CAN FD vehicles with HDA2 (ADAS module equipped)** Use an aftermarket harness, connected to the ADAS module.
* Please note that not all vehicles are supported.

<div align="center" style="text-align: center;">

<h1>carrotpilot</h1>

<h3>
  <a href="https://g4iwnl.gitbook.io/carrotpilot">Manual</a>
</h3>

![image](https://github.com/user-attachments/assets/4d80d256-7e66-4473-a289-04a50733b7e0)


<div align="center" style="text-align: center;">

<h1>openpilot</h1>

<p>
  <b>openpilot is an operating system for robotics.</b>
  <br>
  Currently, it upgrades the driver assistance system in 275+ supported cars.
</p>

<h3>
  <a href="https://docs.comma.ai">Docs</a>
  <span> · </span>
  <a href="https://docs.comma.ai/contributing/roadmap/">Roadmap</a>
  <span> · </span>
  <a href="https://github.com/commaai/openpilot/blob/master/docs/CONTRIBUTING.md">Contribute</a>
  <span> · </span>
  <a href="https://discord.comma.ai">Community</a>
  <span> · </span>
  <a href="https://comma.ai/shop">Try it on a comma 3X</a>
</h3>

Quick start: `bash <(curl -fsSL openpilot.comma.ai)`

![openpilot tests](https://github.com/commaai/openpilot/actions/workflows/selfdrive_tests.yaml/badge.svg)
[![codecov](https://codecov.io/gh/commaai/openpilot/branch/master/graph/badge.svg)](https://codecov.io/gh/commaai/openpilot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![X Follow](https://img.shields.io/twitter/follow/comma_ai)](https://x.com/comma_ai)
[![Discord](https://img.shields.io/discord/469524606043160576)](https://discord.comma.ai)

</div>

<table>
  <tr>
    <td><a href="https://youtu.be/NmBfgOanCyk" title="Video By Greer Viau"><img src="https://github.com/commaai/openpilot/assets/8762862/2f7112ae-f748-4f39-b617-fabd689c3772"></a></td>
    <td><a href="https://youtu.be/VHKyqZ7t8Gw" title="Video By Logan LeGrand"><img src="https://github.com/commaai/openpilot/assets/8762862/92351544-2833-40d7-9e0b-7ef7ae37ec4c"></a></td>
    <td><a href="https://youtu.be/SUIZYzxtMQs" title="A drive to Taco Bell"><img src="https://github.com/commaai/openpilot/assets/8762862/05ceefc5-2628-439c-a9b2-89ce77dc6f63"></a></td>
  </tr>
</table>


Using openpilot in a car
------

To use openpilot in a car, you need four things:
1. **Supported Device:** a comma 3/3X, available at [comma.ai/shop](https://comma.ai/shop/comma-3x).
2. **Software:** The setup procedure for the comma 3/3X allows users to enter a URL for custom software. Use the URL `openpilot.comma.ai` to install the release version.
3. **Supported Car:** Ensure that you have one of [the 275+ supported cars](docs/CARS.md).
4. **Car Harness:** You will also need a [car harness](https://comma.ai/shop/car-harness) to connect your comma 3/3X to your car.

We have detailed instructions for [how to install the harness and device in a car](https://comma.ai/setup). Note that it's possible to run openpilot on [other hardware](https://blog.comma.ai/self-driving-car-for-free/), although it's not plug-and-play.

### Branches
| branch           | URL                                    | description                                                                         |
|------------------|----------------------------------------|-------------------------------------------------------------------------------------|
| `release3`         | openpilot.comma.ai                      | This is openpilot's release branch.                                                 |
| `release3-staging` | openpilot-test.comma.ai                | This is the staging branch for releases. Use it to get new releases slightly early. |
| `nightly`          | openpilot-nightly.comma.ai             | This is the bleeding edge development branch. Do not expect this to be stable.      |
| `nightly-dev`      | installer.comma.ai/commaai/nightly-dev | Same as nightly, but includes experimental development features for some cars.      |

To start developing openpilot
------

openpilot is developed by [comma](https://comma.ai/) and by users like you. We welcome both pull requests and issues on [GitHub](http://github.com/commaai/openpilot).

* Join the [community Discord](https://discord.comma.ai)
* Check out [the contributing docs](docs/CONTRIBUTING.md)
* Check out the [openpilot tools](tools/)
* Read about the [development workflow](docs/WORKFLOW.md)
* Code documentation lives at https://docs.comma.ai
* Information about running openpilot lives on the [community wiki](https://github.com/commaai/openpilot/wiki)

Want to get paid to work on openpilot? [comma is hiring](https://comma.ai/jobs#open-positions) and offers lots of [bounties](https://comma.ai/bounties) for external contributors.

Safety and Testing
----

* openpilot observes [ISO26262](https://en.wikipedia.org/wiki/ISO_26262) guidelines, see [SAFETY.md](docs/SAFETY.md) for more details.
* openpilot has software-in-the-loop [tests](.github/workflows/selfdrive_tests.yaml) that run on every commit.
* The code enforcing the safety model lives in panda and is written in C, see [code rigor](https://github.com/commaai/panda#code-rigor) for more details.
* panda has software-in-the-loop [safety tests](https://github.com/commaai/panda/tree/master/tests/safety).
* Internally, we have a hardware-in-the-loop Jenkins test suite that builds and unit tests the various processes.
* panda has additional hardware-in-the-loop [tests](https://github.com/commaai/panda/blob/master/Jenkinsfile).
* We run the latest openpilot in a testing closet containing 10 comma devices continuously replaying routes.

Licensing
------

openpilot is released under the MIT license. Some parts of the software are released under other licenses as specified.

Any user of this software shall indemnify and hold harmless Comma.ai, Inc. and its directors, officers, employees, agents, stockholders, affiliates, subcontractors and customers from and against all allegations, claims, actions, suits, demands, damages, liabilities, obligations, losses, settlements, judgments, costs and expenses (including without limitation attorneys’ fees and costs) which arise out of, relate to or result from any use of this software by user.

**THIS IS ALPHA QUALITY SOFTWARE FOR RESEARCH PURPOSES ONLY. THIS IS NOT A PRODUCT.
YOU ARE RESPONSIBLE FOR COMPLYING WITH LOCAL LAWS AND REGULATIONS.
NO WARRANTY EXPRESSED OR IMPLIED.**

User Data and comma Account
------

By default, openpilot uploads the driving data to our servers. You can also access your data through [comma connect](https://connect.comma.ai/). We use your data to train better models and improve openpilot for everyone.

openpilot is open source software: the user is free to disable data collection if they wish to do so.

openpilot logs the road-facing cameras, CAN, GPS, IMU, magnetometer, thermal sensors, crashes, and operating system logs.
The driver-facing camera is only logged if you explicitly opt-in in settings. The microphone is not recorded.

By using openpilot, you agree to [our Privacy Policy](https://comma.ai/privacy). You understand that use of this software or its related services will generate certain types of user data, which may be logged and stored at the sole discretion of comma. By accepting this agreement, you grant an irrevocable, perpetual, worldwide right to comma for the use of this data.
