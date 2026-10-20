# V0_demo04：12.5 mm 器皿、原 A 座与受限诊断

2026-10-20｜`V0_demo04/native_nominal`｜完整任务状态：**BLOCKED**｜真实校准：**false**

> **本轮没有完整原座装载成功。** 器皿名义尺寸已按用户更正为 **12.5 × 12.5 × 67.5 mm**，仅统一缩放 XY，Z、高度及底部基准保持。单仪器和最终朝向的静态检查通过，但原 A/B 座仍与杯壁材料相交，已观察点深度约 **0.581 / 0.579 mm**。原座没有扩孔、删件或以碰撞参数改变配合。三次真实受限诊断中，前两次止于搬运滑移/持物偏差，第三次完成座口上方停止、上抬与保持；均没有插入、支撑转移、松爪或完整撤离。固定 5 次、随机 10 次完整任务均未执行，不能填写成功率。

## 1. 任务与器皿派生

本轮保持单台原仪器、完整白色 6 × 6 源架、淡色源杯及蓝色邻杯。源槽工程 ID 为 A1，蓝色邻杯为 F6；目标沿用用户选择的仪器内部原 A 座，即远铰链座 `candidate_far_hinge`。A/B 任务角色已确认，厂家命名、真实公差与相机外参仍未确认。

尺寸来自实际顶点及完整局部变换；机身按明确源 prim 路径识别。下表小数用于追溯浮点网格，不代表真实制造或控制精度；完整坐标系、来源及 prim 见[跨源文件、派生与世界坐标尺寸表](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/dimensions/dimensions.csv)。

| 项目 | 名义尺寸 / 声明 | 实际输入几何与边界 |
| --- | --- | --- |
| 仪器机身局部包络 | 原源 / 派生保持 | 均为 520.5 × 630.0 × 230.0 mm |
| 原开盖整装配 | 原源盖板姿态 | 520.5 × 634.624772 × 435.480987 mm |
| 派生开盖整装配 | 继承近 90° 盖板姿态 | 520.5 × 630.0 × 576.999999 mm；盖板刚体姿态不同，不是整机拉伸 |
| 最终整装配世界 AABB | 仪器 root yaw 135° | 813.172798 × 813.172798 × 576.999999 mm；旋转后的投影包络，不是部件尺寸变化 |
| 原器皿视觉包络 | 14.85 × 14.85 × 67.5 mm | 14.8500055 × 14.8500055 × 67.4999952 mm；原文件保留 |
| 派生器皿视觉包络 | 12.5 × 12.5 × 67.5 mm | 12.5000048 × 12.5000048 × 67.4999952 mm |
| 派生碰撞输入并集包络 | 同一器皿，28 块输入 | 12.5000054 × 12.5000054 × 67.4999956 mm；不等于烹饪后全表面误差 |
| 原 A/B 座外包络 | 保持源 CAD | 每座约 20.4 × 20.4 × 29.0 mm；全部凸起保留 |
| 原座中央参考宽 | 12.6 mm | 若干中央截面边界间距，不是全深度有效方孔净宽 |
| 候选承托 / 插入深度 | 座底上 2 mm / 插入 27 mm | 中央下射线最高表面命中点，未由实物或物理装载确认 |
| 顶框内伸特征 | 每座两处 | 各约 0.8 × 1.5 × 1.0 mm，与座体属于同一 Mesh，功能未知 |
| 源架 / 槽设计尺寸 | 未实测的工程假设 | 架体 110 × 110 × 28 mm，槽内 16 × 16 × 25 mm，底 3 mm、壁 2 mm |

派生变换为 `diag(12.5/14.85, 12.5/14.85, 1)`。视觉材料网格与全部 28 块厚壁碰撞输入应用同一变换；拓扑、全部 Z 顶点、底部 Z=0、其余材质与接触参数保持，没有局部壁形让位。这是授权的新尺寸假设器皿，不能称作原 CAD 已纠正或真实型号已配套。源架槽内宽 16 mm，对新器皿有 1.75 mm 名义单边宽度余量；它与目标原座的配合关口不同。

质量仍为 **20 g 工程假设**。闭合、定向一致的实际视觉材料边界积分给出质心、完整惯量张量与主轴；固定质量后推算同质密度约 5554.83 kg/m³，不是实测材料密度。派生质心 Z 约 29.027633 mm，主惯量约 `[0.8117794, 9.3572084, 9.3572088] × 10⁻⁶ kg·m²`。采用完整仿射二阶矩关系、独立 trimesh 积分及 USD 重载核对，没有使用单一等比 `s²` 规则或重叠凸包体积和。

独立重载的 942 项非预期修改属性与 88 项关系均一致；质心和惯量为有意重算项。新目录复建得到逐字节相同的 USD。13 个高度截面检查覆盖杯底至杯口，均为 CPU 输入几何检查，未读取 PhysX 烹饪形状的完整表面。详见 [器皿证据](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/vessel/README.md)、[实际尺寸](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/vessel/mesh_dimensions.csv)及[质量与惯量](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/vessel/mass_properties.csv)。

## 2. 原 A/B 座为何仍受阻

加密核查重新读取原始三角网格，原 A 为目标、原 B 为对照，没有使用 16 mm 工程适配座。两座结论均为 `BLOCKED_ORIGINAL_MATERIAL_INTERSECTION`。

| 核查项 | 原 A | 原 B |
| --- | --- | --- |
| 声明终态插入深度 | 27.000 mm | 27.000 mm |
| 终态真实截面交叉的采样层 | 21 层 | 21 层 |
| 已观察座边界点落入杯材料的最大点深度 | 0.580803 mm | 0.579034 mm |
| 25 µm 纵向加密中首次已观察交叉深度 | 0.025 mm | 0.025 mm |
| ±50 µm XY、±0.5° yaw 的有限终态诊断 | 45 姿态均交叉 | 45 姿态均交叉 |

点深度是“落入闭合杯材料的座边界点到实际杯三角面的距离”，属于材料相交见证，不能当作全局误差、接触精度或孔径修正量。截面间距为 50 µm，首次观测交叉不是严格最早接触；45 个离散姿态也没有证明所有连续姿态或斜插路径都不可能。

顶框内伸块/薄片约在 X ∈ [−5.5, −4.7] mm、Y ∈ ±[4.8, 6.3] mm、Z ∈ [28, 29] mm，偏离中央宽度采样线。源命名、属性与材质不足以证明它是可退让弹片，没有已知弹性参数或独立可动件。薄片几何和金属外观不能替代机械依据，因此保留刚性源座，不扩孔、删凸起、缩碰撞体或使用负 `rest_offset`。

![原 A/B 座与派生器皿的截面配合](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/geometry/refined_02/native_pair_sections.png)

图 1：CPU 实际三角面截面核查，不是物理插入轨迹。详见[加密核查](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/geometry/refined_02/README.md)与[内伸特征身份](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/geometry/refined_02/source_feature_identity.json)。

完整任务入口已实际调用：[native_gate_01](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/native_gate_01/run_status.json) 在创建仿真应用前返回 `GEOMETRY_BLOCKED_NOT_EXECUTED`，物理执行为 false。这是实际软件关口验证，不是一次物理插入失败。允许的受限诊断只抓取、搬运至座口上方 1 mm、上抬 10 mm 并保持，不插入、不松爪；当前停止线世界 Z=0.915 m。离线审计另给出的座最高三角面上方 0.5 mm 只涉及座几何，不能代替整手、腔壁和整臂净空检查。

## 3. 单仪器朝向与最终静态场景

仪器只有一个 `/World/Instrument` 根节点；原 A/B、8 个视觉实例及 8 个仪器碰撞输入保留，没有第二台仪器或工程适配座。源固有 X90、mm→m 归一化、继承近 90° 盖板派生及本轮 root yaw 在各自层级仅处理一次。

几何上，铰链轴沿 local X，A 比 B 更远离铰链，local +Y 定义为接近侧。仪器原点 `[0.36, 0.18, 0.74] m`、源架中心 `[−0.04, −0.22, 0.74] m` 按 `atan2(架−仪器)−90°` 得到 **仪器 yaw 135°**；旋转后 local +Y 与原点到源架方向一致。没有直接假设翻转 180°。A 自身到架中心仍约 19.7° 离轴，该朝向不证明全路径对齐。依据见[朝向复核](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/scene_orientation/README.md)。

最终 `static_final_01/trial_00` 使用**源架 yaw −45°、仪器 yaw 135°、主相机 1.1 cm（11 mm）**。实际静态检查通过单仪器、原 A/B 激活、无适配座、36 槽 / 50 架碰撞体、28 杯碰撞输入、朝向与复位检查；**任务物理步数为 0**。配置 SHA256 为 `20c19a663b9bbb587595c25af44c75ef1296dd0376d411547be0358eb5d7d873`。它证明最终场景组成，不是连续任务成功或真实相机校准。

![最终静态总览](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/scene_check/final_static_overview.png)

图 2：最终配置实际零任务步预览，画面明确标注原座几何受阻。原始结果见[静态检查](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/scene_check/final_static_static_validation.json)。早期 `static_02` 的源架 yaw 为 135°、主相机 1.3 cm；其屏幕源槽位置和有收敛噪声的近景不作为最终配置图。

## 4. 50 µm 名义余量与实际控制

理想 12.6 mm 刚性方孔与 12.5 mm 杯的单边余量只有 50 µm。以下是同一横向轴上共同占用余量的预先工程分配，不是实测达标值；当前原座不是全深度理想方孔，前提尚不满足。

| 分配项 | 候选值 | 单边占用 |
| --- | --- | --- |
| 入口处杯轴线的实际 XY 分量 | 15 µm | 15.000 µm |
| 27 mm 段实际 tilt | 0.02° | 9.424778 µm |
| 实际 yaw 半包络增量 | 0.1° | 10.898783 µm |
| 合计 / 名义剩余 | — | 35.323561 / 14.676439 µm |

剩余须覆盖尺寸公差、几何表示/烹饪、实际跟踪和抖动、坐标估计等，当前缺少完整实测上界，**预算没有闭合**。15 µm 指入口处实际杯轴线误差，不能拿名义注入量、TCP 目标或 IK 残差替代。抓取点距杯底 53 mm：若误将 XY 分配放在 TCP，0.02° 杠杆横移约 18.500491 µm，同样分配仅余 5.600726 µm；27 mm 与 53 mm 对应不同参考点，不能机械相加。

`contact_offset=50 µm` 是接触生成参数，不是定位精度；`rest_offset=0` 保持。原座约 0.58 mm 的材料相交不能用这份预算放行。质量、摩擦、机器人动力学仍未真实校准。完整推导见[budget.md](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/geometry/budget.md)。

## 5. 三次真实受限诊断

`diagnostic_01/run/trial_00` 实际采用 CPU PhysX / TGS、240 Hz 物理、60 Hz 控制，每控制周期 4 个显式子步。示教器使用物体真值状态，因此不构成视觉策略性能验证。

| 项目 | 首次真实记录 |
| --- | --- |
| 终止原因 | `GRASP_SLIP_DURING_TRANSPORT` |
| 仿真 / 完整进程时间 | 29.5 s / 105.225806 s；执行器内部计时另为 85.507558 s |
| 数据量 | 1770 个完整控制转换；7080 任务物理步，含初态共 7081 条物理记录 |
| 实际阶段 | RESET → APPROACH_SOURCE → GRASP → EXTRACT → TRANSPORT |
| 已通过的子条件 | 初始支撑、实际双指接触、实际离架；已到目标区域 |
| 未完成 | 搬运滑移关口、受控座口上方停止与上抬；没有 INSERT / SUPPORT_TRANSFER / OPEN / RETREAT / VERIFY |
| 独立判分 | workflow / native_pair / data_eligible 均 false；diagnostic_subtask_completed=false |
| 撤离后稳定 | 窗口 unavailable，stable_after_retreat=null；不能按稳定或不稳定装载分类 |

末态器皿**刚体原点**为 `[0.364128530, −0.033040866, 0.973499417] m`；声明目标承托点为 `[0.361616575, −0.030396009, 0.887] m`。仪器局部 XY 偏差为 `[−3.646417, +0.093976] mm`，tilt 为 3.595356°。两指接触力约 7.99962 / 8.00126 N，但从 GRASP→EXTRACT 实际事件（t=13.5 s）到末态的手内相对位置已漂移 **3.758946 mm**。仍有双指接触不等于没有滑移，也没有达到插入预算。数值见[末态与手内漂移记录](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_01/terminal_metrics.json)。

独立检查记录没有禁止的机器人环境接触，且显式子步连续；原座穿透测量仍 unavailable，原生速度与位姿差分的不一致保留为质量标记。末态前三秒仍在搬运，窗口位移不能解释为松爪后的稳定性。原始失败和未知值均保留，不补造后续阶段。依据见[实际结果](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_01/result.json)、[独立判分](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_01/independent_score.json)、[运行参数](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_01/runtime.json)及[完整进程计时](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_01/driver_result.json)。

| 补充受限诊断 | 变更与实际结果 |
| --- | --- |
| [diagnostic_02](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_02/independent_score.json) | 仅将搬运用时 8→16 s；37.5 s 时以 `HELD_POSE_DEVIATION_AFTER_TRANSPORT` 停止。2250 转换、9000 任务物理步 / 9001 记录；完整进程 132.179511 s、内部 108.726389 s。[末态](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_02/terminal_metrics.json)局部 XY `[−3.416480, +0.102169] mm`，仍未通过原 3 mm 阶段关口；没有对准、插入、松爪或撤离。 |
| [diagnostic_03](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_03/independent_score.json) | 保持 16 s 搬运，只在末 1 s 加入有界物体真值 XY 反馈，3 mm 阶段关口不变。76.916667 s 以 `GEOMETRY_BLOCKED_PREINSERT` 结束；4615 转换、18460 任务物理步 / 18461 记录，完整进程 265.300017 s、内部 222.501345 s。十项受限诊断检查均 true，diagnostic_subtask_completed=true；workflow / native_pair / data_eligible 仍 false。 |

第三次实际进入 ALIGN，并在 t=73.416667 s 以最低杯底 Z=0.915019 m 停在原座口上方约 1.019 mm；随后进入 GATE_RETRACT，上抬约 10.015 mm，于 t=75.916667 s 进入 DIAGNOSTIC_HOLD，保持至结束。末态最低杯底 Z=0.925035 m，刚体原点的局部 XY 约 `[14.24, 27.69] µm`，tilt=3.357221°。末段真值反馈帮助通过搬运阶段位置关口，但不等于达到插入预算；这些 XY 读数仍须换算到入口平面，倾角也远大于候选 0.02°。

该上抬是持物状态下的受限诊断动作，没有 INSERT / SUPPORT_TRANSFER / OPEN / RETREAT / VERIFY。原座穿透仍为 null，撤离后窗口 unavailable、stable_after_retreat=null；末三秒包含上抬，不能当作松爪后的稳定窗口。它不改变原座几何受阻、完整任务未执行的结论。详见[末态与停止事件](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_03/terminal_metrics.json)及[控制转换记录](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/results/diagnostic_03/control_trace.csv)。

固定 5 次和随机 10 次只有在原配几何有效且至少一次完整任务独立判分成功后才能启动。配置中 A1/A2/B1/B2/C1 及整架/整仪器各 ±1 mm 平移仅是后续随机化范围，未执行，不是实际误差或成功率。

## 6. 自含诊断数据与录像

两份真实诊断均已导出完整自含 `episode_data.hdf5`。01 为 **1770 转换、314,819,825 字节**，SHA256 `8206d3d9f89c85dff71b198a7916a04fde2960bbf701debf460a6f8bcf3af8dc`；03 为 **4615 转换、885,164,015 字节**，SHA256 `65c32000917083544db3f881054dbf4706a606fcc368002332caf7ccf564e6b0`。各自 52 个源数据集的形状、类型及完整逻辑值核验通过，原 H5 不变，无外链、软链、虚拟数据集或外部存储，原属性与完整任务 false 标签保留。详见[01 导出审计](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/data_audit/diagnostic_01_portable_audit.json)、[01 独立复核](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/data_audit/diagnostic_01_portable_independent_check.json)、[03 导出审计](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/data_audit/diagnostic_03_portable_audit.json)及[03 独立复核](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/data_audit/diagnostic_03_portable_independent_check.json)。

RGB 每路单帧为 `3 × 256 × 256`，01/03 各有 1770/4615 帧；动作/状态为 8 维，完整九维位置命令、每周期 effort 上限及原始指位目标另外保存，并与后继时间端点对齐；未知值用 NaN/false。`agent_pose` 第八维为左指实测位置，`actions` 第八维为左指命令，八维位置目标不含 effort 上限。

正常 `MinimalPickDataset` 构造器明确拒绝两份完整任务未成功的 episode。诊断读取保持原 false 标签，仅复用现有 `__getitem__` 与 `collate_fn`；在起点、中点、末段和最后单步核对动作、状态、RGB 和 padding，通过 `[1,16,8]` 动作 batch 读取。它们没有进入学习成功索引，没有训练、推理或物理回放；`read_batch.npz` 只是样本，不替代完整 H5。

首次诊断的[主视角录像](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/failure_transport_main.mp4)与[近景录像](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/failure_transport_closeup.mp4)来自同一次连续运行，已转为 H.264/yuv420p 并完整 CPU 解码通过；主录像 1920×1080、30 fps、29.534 s，另有原录像 20.5 s 起的末段剪辑，没有混拼其他尝试。[媒体清单](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/manifest.json)绑定源文件与转码 SHA。第二次的[末 5 秒片段](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/failure_02_held_deviation_last5s.mp4)来自其原录像 32.5 s 至结束，也通过完整解码。叠字“target base Fz”实际表示整个目标座网格的合力 Z 分量，未隔离底面支撑，不能用来证明触底。DOCX 仍采用包内 `media/` 相对链接，不内嵌 MP4，转发时须保留完整阅读包。

第三次的[完整主录像](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/preinsert_diagnostic_03_main.mp4)及[对准、上抬与保持片段](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/preinsert_diagnostic_03_align_upward_hold.mp4)已完整 CPU 解码通过。原生高分辨率近景被手爪遮挡；实际 H5 的[第二观测视角片段](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/preinsert_diagnostic_03_obs256_camera2_65s_end.mp4)可看到杯、手指和座口，源分辨率 256×256，显示仅逆时针旋转 90°并近邻放大 2 倍，没有新仿真或补帧。它不能量化 50 µm 间隙，几何停止高度仍依据实际顶点记录。来源、转码与显示处理见[第三次媒体清单](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/media/preinsert_diagnostic_03_manifest.json)。

旧 V0_demo03 阅读包的 6 个 MP4 均存在、可识别且完整 CPU 解码通过，SHA 与旧 manifest 一致。旧 DOCX 使用指向相邻 `media/` 的**外部相对链接，没有内嵌视频**；单独复制 DOCX 不携带这些文件，需传递整个阅读包或直接打开 MP4。具体阅读器点击失败的原因仍未知，旧包未修改，旧录像不计入本轮新结果。依据见[旧包媒体审计](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/data_audit/demo03_package_media_audit.json)。

## 7. 旧版本保护与下一项有效证据

2026-10-20 15:01:27（+08:00）的只读保护核查以既有清单重读 6067 文件，均一致；这证明相对既有基准的累计一致性，不是本轮开工新快照。V0_demo02 按历史提交核对 108 受管文件（普通 Git 64、实际 LFS 44），V0_demo03 核对 420 件（普通 Git 387、实际 LFS 33），均一致。

V0_demo02 的 42 个、V0_demo03 的 1085 个 ignored 输出仅核对存在性及大小，缺少本轮开工前完整哈希快照，故全部旧输出相对开工前逐字节未变仍为未知。本地/只读远端 main 当时均为 `8df72784265c375a327ffa3f0a0cf8c676f229a7`，未改写。范围见[保护证据](/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_demo04/preservation.md)。

解除完整原座阻塞仍需补足：两处内伸特征的真实用途、刚性/弹性及可用行程；12.5 mm 实物杯完整轮廓与公差，尤其底部圆角/倒角与局部避让；原座承托基准、实际装载方向/深度及配套关系的局部图或制造依据。A/B 用户任务角色无需因此重选。
