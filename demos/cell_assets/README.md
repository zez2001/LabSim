# 单细胞前流程设备资产

本入口复用已有模型，为 LabSim 提供固定版本下载、URDF／STL（含多部件装配）→ USD 导入、场景加载和物理装载示例。
当前可加载 **6 项几何资产：3 台设备、1 个磁珠分离架体及 2 个仪器打印件装配**，其中 IKA 为温控／混匀类别的部分替代、MagSep 为管式架体、DIYNAFLUOR 和 OpenFlexure Cell Counter 为打印机械件装配；已完成 IKA 的 **预开盖装载对照及连续开盖—装载—关盖验证**（同一设备的两种流程）。
已有第二台交互设备 **DIYNAFLUOR**：复用原始遮光帽，已完成取帽—停放释放—重新抓取—盖回的 39 秒连续接触验证；不包含样品管装载或荧光测量。
新增 **Flex × MagSep 空架体装载／取回**，同一连续机械臂流程 32/32 通过，覆盖两类资产的限定操作；不含移液、插管或磁分离。OpenFlexure 已尝试原装夹爪取放，接近碰撞未通过。

另有 **1 项固定辅助资产：Poseidon 显微支架**。共 7 个注册条目；辅助支架不计为第 2 类单细胞处理整机，不增加设备类别覆盖。
未取得合适源模型的设备保持待补资料，不生成占位设备，不计入可用数量。

## 范围与可行性

清单按输入设备的 11 类编号对应，型号不代表采购选型或真机兼容认证。

| 类别 | 清单参考 | 当前选择／结论 | 验证与缺口 |
| --- | --- | --- | --- |
| 1 自动细胞计数仪 | Countess 3 FL | **OpenFlexure Cell Counter 打印件装配** | 复用 24 个打印件实例，加载与双视角截图通过；安装孔、计数室及照明连接面已核对。原方案为明场细胞悬液计数，不支持活死染色。电机、相机、镜片、电子元件及盖玻片未建模；计数算法和机构运动未接入。 |
| 2 液滴单细胞处理 | 达普 Galaxy | 待补整机模型；已取得局部 CAD 与参考资料 | Galaxy 官网现可访问，提供产品图和 28×36×22 cm 尺寸（未标轴向）；已下载 Drop-seq 芯片 DWG、Poseidon 泵／显微支架 STEP，另有 HyDrop 芯片论文。它们不是 Galaxy 整机或已装配验证的替代设备，芯片许可、接口及完整装配仍需核实。 |
| 3 微孔单细胞处理 | Singleron Matrix NEO | 待补整机模型；已取得参考及替代路线 CAD | 已取得官方页面、宣传页与产品说明；官网 370×270×230 mm 与宣传页 360×260×230 mm 存在冲突。Seq-Well 作者公开四份装置／模具 DWG，许可为 CC BY-NC-ND 4.0；不计为 Matrix NEO 整机，也不默认允许改编分发。 |
| 4 液体处理工作站 | Hamilton STAR | **Opentrons Flex 单通道 5–1000 µL** | 直接复用 ChemLab；加载、碰撞及双视角截图通过。品牌、通道数、工位与控制 API 均不同，不移植 STAR 参数。已通过 Franka 空架体工位装载／取回；移液和液体动力学未验证。 |
| 5 PCR 热循环仪 | Bio-Rad T100 | **Bio-Rad CFX Opus 96** | 直接复用 ChemLab；加载、碰撞及双视角截图通过。实时荧光 PCR 仪，可覆盖热循环设备外观与机构类别，不等同于 T100 尺寸、远程接口或无人值守能力。 |
| 6 磁珠纯化模块 | DynaMag-96 | **MagSep Rack 管式架体，部分替代** | 直接复用开源 12 管打印架体，加载和双视角截图通过，新增空架体搬运／释放／取回通过；支持作者指定的 1.5–2.0 mL 管。不是 96 孔板几何，源文件不含另购磁铁。毫米尺度为工程推断，管孔兼容及磁分离性能未验证。早期 Alpaqua GLB 为零尺寸，未采用。 |
| 7 温控／混匀模块 | INHECO CPAC | **IKA KS 4000 i control，部分替代** | 恒温轨道摇床，覆盖加热孵育／混匀类别；加载与 Franka 装载通过。不覆盖 CPAC 冷却、紧凑占位或试管／板适配。CPAC 页面只有手册等资料；PyLabRobot Prep heater shaker GLB 内容为平台边框／标签，未采用。 |
| 8 核酸片段分析仪 | Agilent 4200 TapeStation | 待补符合机构要求的整机 | 已取得 TapeStation 官方手册；ChemLab 的 SCIEX PA 800 Plus 有整机几何和 DNA 应用依据，但源模型将真机外罩四连杆简化成单铰链、托盘静态，按本次关节拓扑要求不纳入。不能用位置回放通过代替真机机构关系验证。 |
| 9 核酸浓度检测仪 | Qubit Flex | **DIYNAFLUOR 打印件装配** | 开源 DNA 荧光定量仪，复用 12 个打印件实例并按源手册装配；加载与截图通过。单管设计，非 Qubit Flex 的 8 管通量。CAD 不含电子元件、光学滤片、线缆、紧固件或样品管；未模拟浓度读数。 |
| 10 机械臂 | 转运设备参考 | 复用现有 Franka | 使用仓库 Franka、现有抓取场景和 Lula IK，完成下述装载演示。 |
| 11 调度系统 | Green Button Go／自研 | 本阶段不纳入 | 不实现 SOP 调度、真机通信或生产设备驱动。 |

调研更新于 2026-10-26。这里的“未见”只描述已检查目录和页面；访问失败不证明厂家没有模型。新增资料不会自动增加已完成资产数量。
缺失设备的下一步输入是可复用 CAD／Blender／网格及许可、关键装载部位尺寸；不自行编造结构。

### 固定辅助资产与机构边界

`poseidon_microscope_support` 直接使用作者三个 STL（Base、Screen Leg Mount、Top Stage）的共同装配坐标，仅作全体一致的单位换算、坐标轴旋转和底面归零。原始三角面与部件相对关系保留，STEP、README 和 BSD-2-Clause 许可一同缓存。它是无活动关节的打印支架，不包括相机、镜头、电子件、芯片或注射泵。

新增资产不能仅凭“可导入”或“能播放动作”入库。URDF 加载前检查单根、无环、唯一父链接、链接引用、关节轴、坐标和限位；这些检查只证明文件结构有效，具体机构仍需核对源资料。PA 800 Plus 的四连杆替代、Poseidon 泵尚未核实的完整装配、Drop-seq 芯片局部 CAD、Seq-Well 设备完整性／派生分发许可缺口，均不作为新增合格整机。

已有展示的适用范围保持明确：CFX 和 Flex 的回放不等于完整接触／驱动验证；IKA 源轨道采用虚拟 XY 自由度，不包含真实偏心连杆；源模型缺少气弹簧，自动流程另加参数未标定的双侧支撑机构；OpenFlexure 为静态打印件，不包含柔性台运动。既有模型和结果保留，但不能称为全部真实机构拓扑已认证。

调用新增支架沿用同一 API 和预览入口：

```bash
python -c "from utils.cell_assets import fetch_asset; print(fetch_asset('poseidon_microscope_support'))"
python -m demos.cell_assets.preview --asset-id poseidon_microscope_support --offline --output /new/path/poseidon-support
```

| 待补类别 | 继续实现需要的最小资料 |
| --- | --- |
| 2 液滴单细胞处理 | 用于单细胞建库的设备或完整微流控装置源模型、芯片／管路接口和装载结构、单位与复用许可。注射泵或喷嘴单件不能直接计为整套设备。 |
| 3 微孔单细胞处理 | 微孔捕获／建库芯片及承载、夹持或装载机构的源模型，部件装配关系、单位与复用许可。普通细胞培养微孔板不能直接作为替代。 |
| 8 核酸片段分析 | 与文库片段长度质控功能对应的仪器源模型，样品位、进样／装载机构和活动边界、单位与复用许可。检测器和电泳卡匣单件不能直接计为整机。 |

上述三类当前不注册可加载资产，也不计入完成数量；收到符合范围的源资料后再导入和验证。
现场测量与完整数据集、benchmark 属于后续工作。

## 环境与文件位置

- 本次实测：Linux、RTX 4090、Python 3.11.17、Isaac Sim 5.1.0、NumPy 1.26.0。
- 下载依赖：`huggingface_hub==0.35.3`；图片／视频：Pillow、OpenCV（本机分别为 11.3.0、`opencv-python-headless==4.11.0.86`）。
- 静态 STL 导入依赖：`trimesh==4.5.1`；不会为开放孔洞生成封闭凸包。
- 沿用本地 Conda `labsim` 环境；不在项目中创建虚拟环境。Isaac 的安装以项目环境说明和 NVIDIA 要求为准。
- 原模型默认位于 `~/SLAI_Lab/labsim/local_assets/<source>/<revision>/`；ChemLab 来自 HF，MagSep、DIYNAFLUOR、OpenFlexure Cell Counter、Poseidon 来自 GitHub 固定提交；OpenFlexure 另保留固定 GitLab 上游 CAD 参考包。可用 `LABSIM_ASSET_CACHE` 或 `--cache` 改变。
- USD、截图、视频和轨迹写入调用者提供的**新目录**，已有目录会拒绝覆盖。
- Git 只保存代码、目录配置、本文档和一个 CPU 测试文件；源模型、结果媒体不提交 Git。

在已装好的环境中，先检查帮助；联网下载时沿用自己的代理环境变量。

```bash
conda activate labsim
python -m demos.cell_assets.preview --help
python -c "from utils.cell_assets import fetch_asset; print(fetch_asset('biorad_cfxopus'))"
```

ChemLab 下载来自上游公开 Hugging Face 数据集；MagSep 直接下载固定 GitHub 提交中的架体 STL、README 和许可证，并检查每个文件的 SHA256。DIYNAFLUOR 下载原始 ZIP、说明及许可，只解压清单明确指定且哈希匹配的 18 份 STL／STEP 文件；未执行上游程序。OpenFlexure 下载固定 GitHub 归档和 GitLab CAD 参考包（不含 LFS 图片），校验后只解压指定 STL、README 和许可。所有来源均不依赖 `main`。
未新建团队 Hugging Face 仓库；如需发布派生 USD，再确认仓库归属、访问权限及资产许可。

## API

实现位置：[utils/cell_assets.py](../../utils/cell_assets.py)，注册表：[catalog.json](../../config/cell_assets/catalog.json)。

| 调用 | 输入与返回 | 运行条件 |
| --- | --- | --- |
| `list_assets()` | 返回注册条目列表；含类别、源路径、尺寸、替代关系及限制 | CPU，无网络；注册不等于所有功能已验证 |
| `get_asset(asset_id)` | 返回指定条目，未知 ID 抛 `KeyError` | CPU，无网络 |
| `fetch_asset(asset_id, cache_root=None, offline=False)` | 下载固定版本源目录与许可文件，返回原始 URDF／STL／装配源 ZIP 的 `Path` | 首次需网络；离线模式检查入口哈希、依赖及许可。GitHub 来源逐文件核对哈希；不会用损坏响应覆盖缓存 |
| `read_contract(asset_id, cache_root=None)` | 返回原始 `asset.contract.json` 字典 | 已缓存；无 contract 的 STL 来源抛 `FileNotFoundError`，不编造行为接口，不执行上游脚本 |
| `convert_asset(asset_id, output_dir, cache_root=None)` | URDF 使用 Isaac 原生导入器；STL 直接转成静态三角网格，多部件按目录中的刚体变换装配，返回 `output_dir/model.usd` | 先启动 `SimulationApp`；源已缓存；输出目录必须不存在 |
| `load_asset(usd_path, prim_path, position_m=(0,0,0))` | 在指定新路径创建父节点及 `Asset` 子节点，返回父 `UsdPrim` | 已有 Z-up、米制 stage；根位移单位米；拒绝覆盖已有 prim |

导入保留源碰撞与关节，固定设备基座，不自行拟合质量、惯量或执行器参数。
URDF 加载后设备关节位于 `<prim_path>/Asset` 下，可使用 Isaac `SingleArticulation` 控制；移动关节采用米／弧度。MagSep、DIYNAFLUOR 和 OpenFlexure Cell Counter 是无关节静态网格，不使用 articulation。
Flex 源 URDF 的多个 effort／velocity 为零且缺少分件惯量，目前不能据此声称运动机构动力学已验证。
PCR、IKA 的分件物理参数也含上游工程假设。

IKA 的透明罩原本包含前、顶、左、右四块网格及碰撞体，固定连接到 `hood_joint`，并非缺少几何。
源 MTL 的 `d=0.06` 经导入成为几乎不可见的 cutout 材质。新转换在派生 USD 中为四块罩板绑定 `OmniGlass`，
显示参数集中在目录的 `glass_display`，使用有反射／折射的透明效果；这些数值是可视化假设，不是实测光学参数。
不修改源文件、网格、碰撞或关节。旧 USD 与旧截图保持原状，重新运行转换／预览入口才会应用新显示效果。
最新展示与必要证据统一在 `~/SLAI_Lab/labsim/results/final/`。

MagSep 源 STL 没有单位字段。按 1.5–2.0 mL 微量离心管、20 单位孔距及作者给出的磁铁英寸规格推断为毫米，导入包围盒为 57.3×127.5×44.55 mm；这不是实测尺寸认证。
仅将 XY 中心及底面归零、设置演示色，143806 个源三角面完整保留；静态碰撞使用原三角面，不填平孔洞，不新增磁铁或容器。
转换后的 USD 元数据保留来源、固定提交、许可、署名、单位依据和原点偏移。

DIYNAFLUOR 使用源 STEP 的毫米单位，并与手册 7.8–8 mm 样品孔说明交叉核对。原文件为打印摆放，装配变换集中记录在目录的 `parts`；不修改原 STL。
12 个实例包含底座、上盖、遮光帽及支座、四脚、滤光模块四件，合计 44448 个源三角面。整体包围盒为 71.34×130.039×60.8 mm。
按原手册文件页 5–16、21–24 和连接面确定刚体姿态；内部模块贴合底座凹槽，上盖及支座样品孔同轴，遮光帽初始化停放。
独立截面检查确认三处底座螺孔、两处发射端螺孔对齐，样品轴线上方无盖体遮挡；这是网格一致性检查，不是实物精度认证。
源商业元件未建模；未加入装配胶带厚度。默认资产导入保持所有部件固定，包括遮光帽。新增 `cap_cycle` 入口将原始遮光帽转为带空腔的动态 SDF 碰撞体，已验证取帽、停放和盖回；样品管装载仍未验证。

OpenFlexure Cell Counter 将 16 个 STL 中的 24 个打印件装配到共同坐标系，完整保留 65742 个三角面；多件排版通过 `selection_bounds_source_units` 选择完整三角面后分别作刚体变换。选择边界切过三角面会报错。
源 OpenSCAD 采用毫米，装配包围盒约 170.598×137.917×201.433 mm。底座、照明、光学支架、脚、齿轮、线槽的变换参考官方 v7 beta5；定制样品架按四个安装孔定位，计数室贴合槽底。
独立检查核对 4 个底座孔、4 个样品架孔、2 个照明安装槽；检查选定连接面的三角面中心点，没有发现超过 0.01 mm 的穿入。该检查有明确范围，不等于全模型碰撞认证或实物标定。
转载 STL 只标明 v7 Beta，不能据此认定与 beta5 的原始构建完全相同；固定转载提交、网格哈希及官方参考源包均保留。
所有打印件固定，打印支撑及 brim 保留；齿轮相位仅为初始装配姿态，未验证啮合与柔性台动力学。电机、相机、镜片、电子元件、紧固件和盖玻片未建模，颜色为演示色。
本配置使用定制样品架和计数室；原样品夹及打印装配工具保留在源包中，不加入场景。

最小调用示例（下载可在启动 Isaac 之前执行）：

```python
from pathlib import Path
from utils.cell_assets import fetch_asset, convert_asset, load_asset

fetch_asset("biorad_cfxopus")
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
from isaacsim.core.api import World

world = World(stage_units_in_meters=1.0)
usd = convert_asset("biorad_cfxopus", Path("results/pcr-usd-new"))
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
  --output "$HOME/SLAI_Lab/labsim/results/pcr-preview-new"
python -m demos.cell_assets.preview --asset-id opentrons_flex_single_5_1000ul --offline \
  --output "$HOME/SLAI_Lab/labsim/results/flex-preview-new"
python -m demos.cell_assets.preview --asset-id ika_ks4000 --offline \
  --output "$HOME/SLAI_Lab/labsim/results/ika-preview-new"
python -m demos.cell_assets.preview --asset-id magsep_rack_12_tube \
  --output "$HOME/SLAI_Lab/labsim/results/magsep-preview-new"
python -m demos.cell_assets.preview --asset-id diynafluor \
  --output "$HOME/SLAI_Lab/labsim/results/diynafluor-preview-new"
python -m demos.cell_assets.preview --asset-id openflexure_cell_counter \
  --output "$HOME/SLAI_Lab/labsim/results/openflexure-preview-new"
python -m demos.cell_assets.transfer --offline \
  --output "$HOME/SLAI_Lab/labsim/results/ika-transfer-new"
python -m pytest -q -p no:cacheprovider tests/test_cell_assets.py
```

每次预览运行 120 步，检查可见几何、碰撞、非空图像，生成 `front.png`、`side.png`、`result.json` 与导入 USD。
实测三台均退出 0：PCR 有 28 个网格／41 个碰撞体，Flex 29／110，IKA 58／119；尺寸与源目录的米制尺寸一致。
MagSep 独立加载测试退出 0：120 步、1 个完整静态网格／碰撞体、0 个关节，正侧面截图已检查。DIYNAFLUOR 同样运行 120 步并退出 0：12 个静态网格／碰撞体、0 个关节，正侧面截图已检查，源面索引与装配后顶点独立比对通过。OpenFlexure 同样运行 120 步并退出 0：24 个静态网格／碰撞体、0 个关节，双视角截图和源几何核对通过。这部分为已有加载证据；整理后的 CPU／GPU 回归结果以交接汇报为准。
这些数字只证明资产加载，不能证明移液、热循环或真实精度。

Franka 演示复用 `demos/minimal_pick/scene.py` 的机械臂、烧杯与抓取物理参数，独立扩展演示桌面并加载 IKA；不改写原场景。
设备盖子初始化为打开，摇床停止。目标来自源模型 `sample_port_1` 碰撞几何，夹爪沿 X 合拢以避开滚轴。
仅通过关节控制、接触与摩擦搬运，不附着物体、不用瞬移冒充抓取。

演示以 120 Hz 运行 21.5 秒、2580 步，输出正面／侧面 MP4、最终截图、`trajectory.jsonl` 和 `result.json`。
记录控制目标、实际关节、物体位置／姿态、双指接触力和末端位置；保存源资产哈希、布局、阶段时长及参数假设。
通过要求同时满足：双指接触、抬升至少 8 cm、目标 XY 误差小于 2 cm、落位高度误差小于 1 cm、夹爪释放、实际撤离至少 12 cm、
最后 3 秒无手指接触、倾角小于 5°且位置变化小于 3 mm。失败或异常返回非零退出码。

历史装载对照实测全部通过：抬升 0.23876 m，XY 误差约 0.00087 m，最终烧杯底面 z=0.87270 m，释放后稳定 3 秒；仿真时钟确认总时长 21.500001 秒。
早期目标靠近滚轴导致碰撞飞出，判为失败；调整装载位置及夹爪朝向后通过。结果包保留一份该失败示例。
这是一条固定布局的物理演示，未验证随机布局鲁棒性、设备运行中的夹持或实物精度。

已知运行提示：Isaac 导入器会针对源 URDF 空 `base_link` 报空视觉引用警告；本次其他分件、纹理和碰撞均已核对。
原 Franka 手指碰撞包含多材质，PhysX 使用默认碰撞材质并给出提示；接触验证基于该实际运行配置。

### IKA 自动开盖：已验证的独立步骤

`hood_open` 从关闭状态开始，机械臂夹住源把手，通过真实接触沿源铰链抬罩至约 74.4°。
罩盖位置仅在初始化时设置为零；运行中关闭罩盖驱动，不使用抓取附着或直接罩盖保持力矩。
路径先检查逆运动学连续性，执行时记录关节目标／实测值、罩角、接触力、气弹簧行程和推力。
输出正侧面视频、派生机构 USD 与判分；输出目录必须不存在。

```bash
# 源模型对照：持续握持；加 --release-test 后松手回落会判失败
python -m demos.cell_assets.hood_open --offline --output "$HOME/SLAI_Lab/labsim/results/ika-open-new"
# 新增气弹簧：开盖、释放、撤离、保持 3 秒、重新抓取、关盖和再次释放
python -m demos.cell_assets.hood_open --offline --gas-springs --close-test --output "$HOME/SLAI_Lab/labsim/results/ika-gas-new"
```

新增机构由 `utils/ika_gas_springs.py` 创建，参数集中在 `config/cell_assets/ika_gas_springs.json`。
每侧含缸筒、活塞杆和安装支架，以球铰—滑动副—球铰连接机身与罩盖；闭环约束独立于源 articulation 树求解。
缸筒和活塞杆保留实体碰撞，连接副内部接触由相邻关节过滤。轴向推力成对作用在两刚体上，每个物理步调用 `step()`；
单独打开导出的 `ika_gas_springs.usdc` 可查看几何和关节，但运行气弹簧力学必须配合此 Python 更新，不能只靠 USD 播放。
源碰撞实例只在派生场景展开以设置毫米级接触裕量，源文件保持原样。

厂家说明书（20000005498c/3729600，02/2022，第 13、25、26 页）只确认双侧两支气弹簧及其大致布置。
安装坐标、杆径、质量、约 148 mm 行程、40–48 N 静态推力和阻尼均是工程假设，**未实物标定，也不是厂家 CAD**。
本变体用于仿真机构研究，不增加已复用整机的数量。独立开关盖入口沿用现有 Franka、固定桌面布局与 26 cm 安装座（完整流程使用下述 36 cm 安装座）；其他质量、摩擦、增益同样未实物标定。

### 连续自动开盖、装载、关盖

```bash
python -m demos.cell_assets.hood_open --offline --load-test --output "$HOME/SLAI_Lab/labsim/results/ika-cycle-new"
```

`--load-test` 自动启用气弹簧及关盖阶段。场景从关闭状态开始，一次连续运行完成开盖、松手保持、
取杯、装载、实际释放、撤离保持、返回关盖和最终稳定；不移动或附着杯子／罩盖来代替物理接触。
布局与参数集中在 `config/cell_assets/ika_automatic_cycle.json`，装载规划及判分在 `loading.py`；
`motion.py` 共享路径数据和连续 IK，`cameras.py` 共享双视角录像，两个流程不再各自维护重复实现。

机械臂底座位于 `[-0.20, -0.20, 1.10] m`，仪器基座位于 `[0.10, 0.45, 0.74] m`；沿用源平台 `sample_port_1`。
从避免肘部碰罩的放置姿态反向计算连续 IK，再沿原关节路径撤回。
开盖阶段夹爪刚度为 10000，杯子操作阶段恢复到原装载演示的 2000，每指驱动上限保持 40 N，避免高刚度抓杯导致夹爪无法释放。
这些增益、安装座及布局均为仿真假设。

验收同时检查开启保持、非把手及桌面／安装座碰撞、稳定抓取、平台落位、夹爪真实张开、释放后撤离 12 cm、
至少 3 秒位置稳定、杯体直立及关盖后的最终保留。遇到大于 5 N 的非预期碰撞、持杯丢失、释放或落位失败时停止；
最终通过还要求非预期接触峰值小于 1 N、全部阶段完成，不能将中途成功算作整段成功。
沿用原模型几何、气弹簧工程假设及现有 conda 环境，不代表真机控制或未经标定的真实精度。

IKA 完整流程证据见 `~/SLAI_Lab/labsim/results/final/evidence/full/`，过程录像与失败对照集中在最终 HTML，原始判定不改写。

### DIYNAFLUOR 遮光帽连续操作

```bash
python -m demos.cell_assets.cap_cycle --offline \
  --output "$HOME/SLAI_Lab/labsim/results/diynafluor-cycle-new"
```

该入口复用已有 12 件装配、Franka、共享连续 IK 和录像模块；只将 `ParkedCap` 原始网格改为自由动态刚体。
帽子原始 14,972 个三角面和空腔保留，采用 256 分辨率 SDF 碰撞，不将空腔封为凸包；其余 11 件固定。
从测量位盖好状态开始，经取帽、抬升、停放、实际释放撤离和 3 秒稳定，再重新抓取、抬升、盖回、释放撤离及最终 3 秒稳定。
执行期间只发送机械臂关节目标，不写帽子位姿、不附着或固定帽子。绿色是展示用改色。

参数集中在 `config/cell_assets/diynafluor_cap_cycle.json`。源支座的两中心相距 41 mm；采用原 STL 和装配手册的坐标，未改变零件尺寸。
按原闭合网格体积及假设 PLA 密度 1240 kg/m³ 得到帽子质量约 5.14 g；摩擦、增益、固定安装和接触偏移均未标定。
夹爪每指驱动力上限 5 N，TCP 在帽子底部上方 16 mm，避免触碰外壳并在直壁位置夹持。

正式运行 120 Hz、4680 步、39.000002 秒，32/32 检查通过。输出正面、侧面和近景 MP4、阶段截图、计划、逐步轨迹、源文件／代码哈希和结果。
检查覆盖完整步骤、实际双指接触、抬升、搬运姿态和偏移、两处落位、真实释放、撤离、稳定及意外碰撞。
这是 **遮光帽机械操作**，不是插管、荧光测量、浓度读数或真机控制。默认 `convert_asset("diynafluor", ...)` 仍保留原静态导入约定。

正式证据在 `~/SLAI_Lab/labsim/results/final/evidence/cap-cycle/`，视频统一内嵌于最终 HTML。

### Flex 与 MagSep 架体装载／取回

```bash
python -m demos.cell_assets.handling --offline --output /new/path/rack-loading
```

复用 MagSep 原始架体，保持所有三角面，只刚体旋转和动态 SDF 转换；Flex 原始工位与碰撞保留。参数集中在 `config/cell_assets/rack_loading.json`，120 Hz、6120 步、51 秒、32/32 通过。验证抓取、工位放置、释放撤离及取回，包含两处 3 秒稳定、真实承重、双指接触与非预期碰撞检查。D2 只是几何放置表面，不是官方耗材适配认证，不包含插管、磁珠纯化、取吸头或移液。

`handling.py` 同时保留 OpenFlexure 原装夹爪的失败复现配置 `config/cell_assets/openflexure_handling.json`：最终接近碰照明支座；另一配置碰样品架，抬高后未形成稳定双指夹持。它不属于已验证装卸能力，需要有尺寸依据的细指／夹具。详细证据与数值见交接汇报。

### 更新唯一 HTML

九类对应与剩余条件维护在 `config/cell_assets/coverage.json`，录像清单在最终包 `evidence/index.json`。第 2、3、8 类展示问号，不注册占位模型。以**最终页面本身**为模板和既有媒体容器，不再依赖旧版 HTML：

```bash
python scripts/update_cell_asset_showcase.py \
  --base "$HOME/SLAI_Lab/labsim/results/final/LabSim数字资产与机械臂演示.html" \
  --evidence "$HOME/SLAI_Lab/labsim/results/final/evidence" \
  --output /new/path/LabSim数字资产与机械臂演示.html
```

已有录像保留字节及原实验标签；仅对新增录像转 H.264 并完整解码检查。当前 19 次运行、40 段内嵌视频。输出必须是新路径，核对后再替换唯一交付文件。旧的 `--layout-only` 专项入口已合并到统一更新入口。

## 来源、许可与交接

完整的固定来源、作者署名、资产许可、候选设备排除理由及来源资料位置见
[来源与调研](../../docs/cell_assets/来源与调研.md)。ChemLab 代码与模型采用不同许可；新气弹簧不是厂家 CAD。

[交接汇报](../../docs/cell_assets/交接汇报.md) 汇总本阶段范围、逐项状态、模块职责、复现顺序、实测验收与未完成事项。
当前按用户要求仅本地整理；未新增提交、推送、PR 或团队 HF 发布。

私有 HF Dataset 镜像已发布：[PercyM/labsim-cell-assets](https://huggingface.co/datasets/PercyM/labsim-cell-assets)，固定版本 `f6b0f9f2dbe5046c0833fb099121e5a551d208f7`。53 个文件（含 40 段 MP4）的远端回读和 SHA256 校验通过；下载后的 GPU 仿真未重跑。按 [发布与调用指南](../../docs/cell_assets/HuggingFace上传指南.md) 下载 `assets/LabSim-digital-assets.zip`，解压后将其根目录设为 `LABSIM_ASSET_CACHE`，再使用现有离线 API。默认上游获取逻辑不变。镜像不含本轮尚未提交的项目代码；GitHub 提交和 PR 尚未执行。
