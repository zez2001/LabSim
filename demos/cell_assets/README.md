# 单细胞前流程设备资产

本入口复用已有模型，为 LabSim 提供固定版本下载、URDF → USD 导入、场景加载和物理装载示例。
当前可加载 **3 台设备**，其中 IKA 为温控／混匀类别的部分替代；完成 **1 个 Franka 物理装载场景**。
未取得合适源模型的设备保持待补资料，不生成占位设备，不计入可用数量。

## 范围与可行性

清单按输入设备的 11 类编号对应，型号不代表采购选型或真机兼容认证。

| 类别 | 清单参考 | 当前选择／结论 | 验证与缺口 |
| --- | --- | --- | --- |
| 1 自动细胞计数仪 | Countess 3 FL | 待补模型 | ChemLab 203 项目录未见对应模型；所查 Thermo 产品页无直接 CAD 链接。需要外形、计数板接口与许可明确的源模型。流式分选仪不作为等价替代。 |
| 2 液滴单细胞处理 | 达普 Galaxy | 待补模型 | 目录未见对应模型；清单资料页本次 TLS 访问超时。需要设备／芯片源模型。NanoAssemblr 是纳米颗粒制备仪，不作为单细胞液滴设备。 |
| 3 微孔单细胞处理 | Singleron Matrix NEO | 待补模型 | 目录未见对应模型；厂家页面本次 TLS 访问失败。需要芯片、装载机构及外形模型。 |
| 4 液体处理工作站 | Hamilton STAR | **Opentrons Flex 单通道 5–1000 µL** | 直接复用 ChemLab；加载、碰撞及双视角截图通过。品牌、通道数、工位与控制 API 均不同，不移植 STAR 参数。移液和液体动力学未验证。 |
| 5 PCR 热循环仪 | Bio-Rad T100 | **Bio-Rad CFX Opus 96** | 直接复用 ChemLab；加载、碰撞及双视角截图通过。实时荧光 PCR 仪，可覆盖热循环设备外观与机构类别，不等同于 T100 尺寸、远程接口或无人值守能力。 |
| 6 磁珠纯化模块 | DynaMag-96 | 待补有效模型 | PyLabRobot 的 Alpaqua Magnum FLX 候选 GLB 网格包围盒为零，不可用。需要有有效几何的磁力架 CAD 与板兼容信息。 |
| 7 温控／混匀模块 | INHECO CPAC | **IKA KS 4000 i control，部分替代** | 恒温轨道摇床，覆盖加热孵育／混匀类别；加载与 Franka 装载通过。不覆盖 CPAC 冷却、紧凑占位或试管／板适配。CPAC 页面只有手册等资料；PyLabRobot Prep heater shaker GLB 内容为平台边框／标签，未采用。 |
| 8 核酸片段分析仪 | Agilent 4200 TapeStation | 待补模型 | 目录未见对应模型；厂家页本次返回 403。需要仪器、样品位及自动装载结构源模型。普通凝胶成像仪不作为等价替代。 |
| 9 核酸浓度检测仪 | Qubit Flex | 待补模型 | 目录未见对应模型；所查 Thermo 产品页无直接 CAD 链接。多功能酶标仪需确认定量方案及容器，当前未认定为等价替代。 |
| 10 机械臂 | 转运设备参考 | 复用现有 Franka | 使用仓库 Franka、现有抓取场景和 Lula IK，完成下述装载演示。 |
| 11 调度系统 | Green Button Go／自研 | 本阶段不纳入 | 不实现 SOP 调度、真机通信或生产设备驱动。 |

调研记录于 2026-10-25。这里的“未见”只描述已检查目录和页面；访问失败不证明厂家没有模型。
缺失设备的下一步输入是可复用 CAD／Blender／网格及许可、关键装载部位尺寸；不自行编造结构。
现场测量与完整数据集、benchmark 属于后续工作。

## 环境与文件位置

- 本次实测：Linux、RTX 4090、Python 3.11.17、Isaac Sim 5.1.0、NumPy 1.26.0。
- 下载依赖：`huggingface_hub==0.35.3`；图片／视频：Pillow、OpenCV（本机分别为 11.3.0、`opencv-python-headless==4.11.0.86`）。
- 沿用本地 Conda `labsim` 环境；不在项目中创建虚拟环境。Isaac 的安装以项目环境说明和 NVIDIA 要求为准。
- 原模型默认位于 `~/LabSim-assets/chemlab/<HF revision>/`；可用 `LABSIM_ASSET_CACHE` 或 `--cache` 改变。
- USD、截图、视频和轨迹写入调用者提供的**新目录**，已有目录会拒绝覆盖。
- Git 只保存代码、目录配置、本文档和一个 CPU 测试文件；源模型、结果媒体不提交 Git。

在已装好的环境中，先检查帮助；联网下载时沿用自己的代理环境变量。

```bash
conda activate labsim
python -m demos.cell_assets.preview --help
python -c "from utils.cell_assets import fetch_asset; print(fetch_asset('biorad_cfxopus'))"
```

下载来自上游公开 Hugging Face 数据集，固定 revision，不依赖 `main`。
未新建团队 Hugging Face 仓库；如需发布派生 USD，再确认仓库归属、访问权限及资产许可。

## API

实现位置：[utils/cell_assets.py](../../utils/cell_assets.py)，注册表：[catalog.json](../../config/cell_assets/catalog.json)。

| 调用 | 输入与返回 | 运行条件 |
| --- | --- | --- |
| `list_assets()` | 返回注册条目列表；含类别、源路径、尺寸、替代关系及限制 | CPU，无网络；注册不等于所有功能已验证 |
| `get_asset(asset_id)` | 返回指定条目，未知 ID 抛 `KeyError` | CPU，无网络 |
| `fetch_asset(asset_id, cache_root=None, offline=False)` | 下载固定版本源目录与许可文件，返回原始 URDF 的 `Path` | 首次需网络；离线模式检查入口哈希、依赖文件、许可文件及 LFS 实体 |
| `read_contract(asset_id, cache_root=None)` | 返回原始 `asset.contract.json` 字典 | 已缓存；不执行上游脚本，不将语义端口当成标定抓取点 |
| `convert_asset(asset_id, output_dir, cache_root=None)` | 使用 Isaac 原生 URDF 导入器，返回 `output_dir/model.usd` | 先启动 `SimulationApp`；源已缓存；输出目录必须不存在 |
| `load_asset(usd_path, prim_path, position_m=(0,0,0))` | 在指定新路径创建父节点及 `Asset` 子节点，返回父 `UsdPrim` | 已有 Z-up、米制 stage；根位移单位米；拒绝覆盖已有 prim |

导入保留源碰撞与关节，固定设备基座，不自行拟合质量、惯量或执行器参数。
USD 加载后设备关节位于 `<prim_path>/Asset` 下，可使用 Isaac `SingleArticulation` 控制；移动关节采用米／弧度。
Flex 源 URDF 的多个 effort／velocity 为零且缺少分件惯量，目前不能据此声称运动机构动力学已验证。
PCR、IKA 的分件物理参数也含上游工程假设。

最小调用示例（下载可在启动 Isaac 之前执行）：

```python
from pathlib import Path
from utils.cell_assets import fetch_asset, convert_asset, load_asset

fetch_asset("biorad_cfxopus")
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
from isaacsim.core.api import World

world = World(stage_units_in_meters=1.0)
usd = convert_asset("biorad_cfxopus", Path.home() / "LabSim-results/pcr-usd-new")
device = load_asset(usd, "/World/PCR", position_m=(0.5, 0.0, 0.0))
world.reset()
for _ in range(120):
    world.step(render=True)
app.close(wait_for_replicator=False)
```

这是 **仿真资产 API**。ChemLab 提供的仪器行为脚本和各厂家的真机 API 没有接入；不生成真实温度、浓度、片段长度或液体移液结果。
用户业务接口应在获得厂家协议后单独适配，不能把模型加载成功视为设备联机成功。

## 复现与验收

每条命令使用新输出目录；单 GPU 顺序执行。去掉 `--offline` 可先下载源文件。

```bash
python -m demos.cell_assets.preview --asset-id biorad_cfxopus --offline \
  --output "$HOME/LabSim-results/pcr-preview-new"
python -m demos.cell_assets.preview --asset-id opentrons_flex_single_5_1000ul --offline \
  --output "$HOME/LabSim-results/flex-preview-new"
python -m demos.cell_assets.preview --asset-id ika_ks4000 --offline \
  --output "$HOME/LabSim-results/ika-preview-new"
python -m demos.cell_assets.transfer --offline \
  --output "$HOME/LabSim-results/ika-transfer-new"
python -m pytest -q -p no:cacheprovider tests/test_cell_assets.py
```

每次预览运行 120 步，检查可见几何、碰撞、非空图像，生成 `front.png`、`side.png`、`result.json` 与导入 USD。
实测三台均退出 0：PCR 有 28 个网格／41 个碰撞体，Flex 29／110，IKA 58／119；尺寸与源目录的米制尺寸一致。
这些数字只证明资产加载，不能证明移液、热循环或真实精度。

Franka 演示复用 `demos/minimal_pick/scene.py` 的机械臂、烧杯与抓取物理参数，独立扩展演示桌面并加载 IKA；不改写原场景。
设备盖子初始化为打开，摇床停止。目标来自源模型 `sample_port_1` 碰撞几何，夹爪沿 X 合拢以避开滚轴。
仅通过关节控制、接触与摩擦搬运，不附着物体、不用瞬移冒充抓取。

演示以 120 Hz 运行 21.5 秒、2580 步，输出正面／侧面 MP4、最终截图、`trajectory.jsonl` 和 `result.json`。
记录控制目标、实际关节、物体位置／姿态、双指接触力和末端位置；保存源资产哈希、布局、阶段时长及参数假设。
通过要求同时满足：双指接触、抬升至少 8 cm、目标 XY 误差小于 2 cm、落位高度误差小于 1 cm、夹爪释放、实际撤离至少 12 cm、
最后 3 秒无手指接触、倾角小于 5°且位置变化小于 3 mm。失败或异常返回非零退出码。

本次最终实测全部通过：抬升 0.23876 m，XY 误差约 0.00087 m，最终烧杯底面 z=0.87270 m，释放后稳定 3 秒；仿真时钟确认总时长 21.500001 秒。
早期目标靠近滚轴导致碰撞飞出，判为失败；调整装载位置及夹爪朝向后通过。结果包保留一份该失败示例。
这是一条固定布局的物理演示，未验证随机布局鲁棒性、设备运行中的夹持或实物精度。

已知运行提示：Isaac 导入器会针对源 URDF 空 `base_link` 报空视觉引用警告；本次其他分件、纹理和碰撞均已核对。
原 Franka 手指碰撞包含多材质，PhysX 使用默认碰撞材质并给出提示；接触验证基于该实际运行配置。

## 来源、许可与交接

- [ChemLab-Assets](https://github.com/mbzuai-nlp/ChemLab-Assets/tree/c711fe1a7a9d26a7efd9d63d2bddc0de62e6b65e)：目录 v1.4.0、203 项。
- [固定 HF 资产版本](https://huggingface.co/datasets/MBZUAI/ChemLab-Assets/tree/a6c006f921c9bee62f5585dd7f769163a7f51573)：保留 Blender、GLB、URDF、分件网格、纹理、碰撞与 contract。
- ChemLab 代码 MIT，**模型／资产数据 CC BY-NC 4.0**；需署名且受非商业限制，第三方例外以其 `NOTICE.md` 为准。本项目代码许可不覆盖这些模型。
- 署名：Zirui Song、Jiadong Zhang、Jiahao Zhang、Xiaosong Ma、Xiaojun Chang、Xiuying Chen，MBZUAI。下载同时保留 `LICENSE`、`LICENSE-ASSETS.md`、`NOTICE.md`、`CITATION.cff`。
- ChemLab 模型基于公开参考资料建立，不是经实物校准的厂家 CAD。本次没有修改上游源文件。
- [PyLabRobot 候选版本](https://github.com/PyLabRobot/pylabrobot/tree/fc5ae129c39ef645a2a11234dce97f933a317a9c)：根许可 MIT；所查 Alpaqua 和 Prep GLB 无法用于本次设备交付，未收录。
- [Opentrons 官方 OT-2 CAD](https://github.com/Opentrons/ot2/tree/ef9ede131ed1d64daf9a0df5b2140a0a8e56b632/reference-model)：存在 STEP/STL；未找到明确根许可，当前未转载为可交付资产。
- [INHECO CPAC](https://www.inheco.com/cpac.html)、[Countess 3 FL](https://www.thermofisher.cn/cn/zh/home/life-science/cell-analysis/cell-analysis-instruments/automated-cell-counters/models/countess-3-fl.html)、[Qubit Flex](https://www.thermofisher.cn/cn/zh/home/industrial/spectroscopy-elemental-isotope-analysis/molecular-spectroscopy/fluorometers/qubit/models/qubit-flex.html)：所查公开页面未提供直接 CAD 链接。

本次统一结果目录为 `~/LabSim-results/cell-assets-20261025/`，包含三台资产截图、成功与失败代表录像、轨迹和先读说明。
源模型留在缓存，结果目录不打包 Python 环境或整个工程。
开发使用单一功能分支 `codex/cell-assets-junjie-20261025`，稳定修改经中文 PR 交给 `codex/labsim` 评审；不直接推送集成分支。
