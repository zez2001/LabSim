# LabSim 亚毫米器皿插入实验报告

实验日期：2026-10-13；分支 codex/precision-insertion；基准提交 302c175。

本轮已实现独立场景、物理夹持插入、偏差扫描、独立判分、双视角采集和录像。当前资产、控制与物理配置能重复区分亚毫米偏差导致的任务结果变化，但失败机制及边界会随接触和求解配置变化，不能据此宣称 Isaac Sim 具有 0.1 mm 真实精度。

默认配置中，名义偏差 0–0.30 mm 的各条件均成功；0.35 mm 起出现非成功。120 Hz 在 0.35 mm 发生底座穿透，240/480 Hz 在同一偏差受阻。已观察到接触引起的被动重新对齐；它不保证最终任务成功。

| 数据组 | 条数 | 成功 | 受阻 | 物理异常 |
| --- | --- | --- | --- | --- |
| 主扫描 | 81 | 45 | 33 | 3 |
| 同实际初态复核 | 36 | 18 | 15 | 3 |
| 接触及迭代单因素 | 9 | 4 | 4 | 1 |
| GUI 主入口中心插入 | 1 | 1 | 0 | 0 |

另完成 12 条无接触微动诊断；原 minimal_pick 专家物理抓取复现成功。3 条原生 USD Cylinder 对照因约 0.100 mm 的查询边界偏差被排除，未计入上表。所有仿真按顺序使用同一张 GPU。

图1 中心插入录像终帧。达到约 20 mm 深度，夹爪打开并撤离，稳定保持 1 秒。；图：`success.png`

工程目录 /home/wujing/Desktop/vla/LabSim；工作分支 codex/precision-insertion，起点 302c175。main 分支与原 minimal_pick 文件未改动。实验源码快照随各运行保存；本报告的数据只取明确列出的正式目录。

## 实际偏差与结果边界

主扫描 X 名义偏差为 0、0.1、0.2、0.25、0.3、0.35、0.4、0.5、0.8 mm，各重复三次。通过初始化沿 −X 移动整个孔座注入偏差，目标轨迹不变。边界处已有 0.05 mm 间距；本轮不推断更细的阈值。

图2 首次检测到孔座接触之前的实际 X 偏差与结果。点为重复运行，不是广泛场景成功率。虚线为 0.3 mm 理想单侧间隙。；图：`primary_actual_offset_outcome.png`

| 物理频率 | 名义成功到非成功区间 | 实际接触前 X 区间 | 右侧结果 |
| --- | --- | --- | --- |
| 120 Hz | 0.30–0.35 mm | 0.27615–0.32615 mm | 物理异常 |
| 240 Hz | 0.30–0.35 mm | 0.27757–0.32757 mm | 受阻 |
| 480 Hz | 0.30–0.35 mm | 0.27339–0.32339 mm | 受阻 |

实际偏差比名义值小约 22–27 µm，主要来自持握与跟踪状态；同初态复核仍重现相同结果分布。三次重复在本机相同条件下得到一致数值。交付图 primary_offset_depth.png 给出偏差与最大深度，primary_injected_actual_offset.png 对照注入与实测。

## 资产与碰撞核查

从空场景启动，不加载 lab_001。复用项目 Franka 资产、桌面、灯光、双相机与 Lula IK 接口；外壳、孔座和不透明试管均为从零生成的合成代理资产，未做真实仪器校准。

| 项目 | 设置或核查结果 |
| --- | --- |
| 试管 | 外径 10.0 mm，长 50 mm，质量 0.02 kg，平底刚体 |
| 孔座 | 内径 10.6 mm，深 20 mm，无倒角；孔口 0.790 m，底面 0.770 m |
| 惯性 | 横向 4.291667×10⁻⁶，轴向 2.5×10⁻⁷ kg m²；重心居中 |
| 碰撞表示 | 管由 96 个六顶点凸楔组成；孔为 128 段静态三角网格，保留空腔 |
| 几何离散误差 | 相对理想圆：管 2.677 µm，孔 1.596 µm |
| 运行时采样 | 重载后管径向最大误差 2.688 µm；端面约 ±25.000 mm |
| 摩擦与恢复 | 管及孔静/动摩擦 0.5/0.4，恢复 0，average；夹指回退值 0.5/0.5/0 |
| 独立资产 | tube.usda 与 module.usda；米制、Z 向上、visual/collision 分离 |

小尺寸整体凸包曾出现烹制粗化，最终采用毫米局部坐标加 0.001 缩放的分段凸体。已读取全部 96 块烹制顶点，并用 384 条径向射线及竖直射线核查孔腔、管壁与底座；完整场景在新进程重载并复位三次。

图3 作者定义的碰撞几何调试视图。孔洞保留，绿色显示碰撞外形；另有烹制数据与 PhysX 查询交叉核查。；图：`collision_debug.png`

限制：没有读取完整运行时孔壁三角形，不能声称所有生效碰撞面已逐面核验。深插入时按运行时夹指姿态及其作者定义包围盒，孔口上方最小间隔约 2.698 mm；这不是完整夹指烹制网格的验证。原生 USD Cylinder 在查询中半径约 5.100 mm、半长约 25.100 mm，来源未定位，故排除该路线。

## 控制判分和记录契约

仅在初始化写入初态。运行后试管保持动态刚体，完全通过夹爪接触运动；未绑定、瞬移、逐帧设位姿或关闭关键碰撞。固定目标 TCP 为 X=0.20 m、Y=0；孔座固定 Y=0.00030 m，用于补偿该持握设置的偏置。

时序为 0–2 s 夹持，2–24 s 以 1 mm/s 下降 22 mm，25–27 s 平滑开爪，27–30 s 撤离 40 mm，30 s 起检查稳定性。无主动搜索、视觉纠偏或恢复。Lula IK 位置容差 10 µm、姿态容差 0.001 rad。

统一成功判据：实际插入深度 18–20.05 mm；两夹指均打开超过 35 mm；TCP 高于孔口至少 35 mm；夹指接触力低于 0.01 N；管体位于孔腔；释放后位置变化小于 0.1 mm、姿态变化小于 0.5°，连续保持至少 1 s；全程几何重叠不超过 50 µm。不同配置共用这些门槛。

独立几何检查使用实际管体位姿及烹制凸体顶点和边，裁剪至孔壁高度范围，检测孔腔半平面与底座侵入，并处理平口有限高度的接触；不只检查物体中心。它适用于本实验接近直立、靠近孔座的状态，并非任意形状的全局精确穿透算法。离线 audit 根据保存状态重新判分，不使用名义偏差标签。

BLOCKED 由有接触、深度不足 18 mm、目标仍下降而实际约 2 s 内下降不足 0.1 mm 判断。代码还提供 GRASP_SLIP、DROPPED、UNSTABLE_AFTER_RELEASE、TIMEOUT、PHYSICS_INVALID、CONTROL_OR_IK_FAILURE；本轮没有逐一进行故障注入验证。

| 记录层 | 内容 |
| --- | --- |
| 每控制步 | 双 RGB 256×256，8 维动作，9 维实际关节，obs/action/next_obs，时间戳与终止标签 |
| 每物理步 | 试管姿态与速度、TCP、关节、偏差、倾角、深度、滑移、接触点法向及力 |
| 每条轨迹 | 初态、事件、结果、仿真与执行墙钟耗时、HDF5、MP4；失败记录保留 |
| 每组配置 | USD、有效参数、几何查询、源代码快照与哈希；成功轨迹按原机制合并 |

120/240/480 Hz 分别执行 2/4/8 个物理步，控制恒为 60 Hz，渲染独立调用。核对引擎时钟、动作保持、后继状态和终止步；接触冲量按当前 physics_dt 换算为力。正式 126 条与 GUI 1 条的离线判分一致，12 条微动记录完成对齐核查。

CPU PhysX、numpy、TGS、CCD、位置/速度迭代 32/8；默认两侧 contact offset 50 µm、rest offset 0。关节驱动继承原资产，臂 Kp 约 5.73×10⁸、Kd 5.73×10⁶、力矩上限 100000；速度上限接近浮点上界。该控制配置未校准为真实 Franka 动态。

## 物理配置敏感性与微动诊断

主扫描只改变物理频率。另从同一实测关节及持握位姿、零速度初始化，比较三个频率各 0、0.30、0.35、0.40 mm，重复三次。初态通过 1 µm 检查；结果仍为 120 Hz 的 0.35 mm 物理异常、240/480 Hz 受阻。全新复位未序列化内部求解器缓存。

针对 120 Hz 边界，逐项比较接触距离和位置迭代，各条件仅一次。管、孔及夹指 contact offset 一起改变，rest offset 始终为零，尺寸未修改。

| 单因素条件 | 0 mm | 0.35 mm | 0.40 mm | 0.35 最大重叠 |
| --- | --- | --- | --- | --- |
| contact 25 µm | 成功 | 异常 | 受阻 | 1.09839 mm |
| contact 100 µm | 成功 | 成功 | 受阻 | 0.04799 mm |
| 位置迭代 64 | 成功 | 受阻 | 受阻 | 0.01279 mm |

contact 100 µm 时，观测到的成功到受阻区间移至 0.35–0.40 mm，但成功轨迹的约 48 µm 重叠已靠近固定 50 µm 容差。这说明结果对数值接触配置敏感；不能称为提高了位置精度，也不足以认定边界在广泛初态中稳定。

原生 Cylinder 的三条早期诊断保留在原目录，但因运行时边界查询与标称尺寸相差约 100 µm 而排除。当前代码在插入前增加 10 µm 几何门槛，拒绝不匹配资产。离线与在线判分一致也不能弥补共同几何参考错误。

| 物理频率 | 0.1 mm 指令实测 | 2 mm 指令实测 | 最大轴保持抖动 |
| --- | --- | --- | --- |
| 120 Hz | 0.100005 mm | 1.999966 mm | 0.002623 mm |
| 240 Hz | 0.100291 mm | 2.000041 mm | 0.007987 mm |
| 480 Hz | 0.104341 mm | 2.004391 mm | 0.000412 mm |

微动诊断还包括 0.5、1 mm，共 12 条，每条 3 s、无孔座接触。平均 TCP 目标误差约 0.010–0.015 mm；480 Hz 相对位移有约 4.4 µm 偏置。IK 残差、关节跟踪及三轴抖动见 data/micro_*.json。这是该控制配置的诊断，不等于机器人绝对定位精度。

在固定初始化下可重复分辨本轮 0.05 mm 网格上的结果变化；尚不能给出跨接触参数不变的 0.05 mm 边界，也没有证据支持小于该步长的结论。无需再以方块落平面替代本轮已经完成的主插入测试。

## 被动重新对齐与穿透异常

120 Hz、名义 0.35 mm 的代表轨迹，在首次接触前实际 X 偏差约 0.326 mm；接触后缩小到约 0.291 mm，并插入到 18 mm 以上。夹持内移动与轻微倾斜允许被动重新对齐，不能按初始偏差直接判失败。

图4 同一完整轨迹中的重新对齐与最终异常。约 25 s 开始释放后，底座重叠超过固定 0.05 mm 容差，最终判 PHYSICS_INVALID。；图：`passive_then_invalid_dynamics.png`

该轨迹终止深度约 20.160 mm，几何底座重叠约 0.163 mm；终端 PhysX 射线定位底面约 Z=0.769840 m，相对 Z=0.770 m 底座出现约 0.160 mm 侵入，支持实际异常判断。此前插入阶段的最大有限孔壁重叠约 0.00956 mm。

passive_alignment_partial.mp4 只截取该轨迹 3.9–23.0 s 的接触及插入过程；完整 physics_invalid.mp4 显示最终失败。两者来自同一次试验，不能把截取片段作为成功样本。

## 建模工作量与后续验证

本轮最费工作的是微小碰撞几何烹制、时钟与接触记录核查，以及持握和释放阶段的数值异常。可见外观的生成很快；可碰撞、可操作、可记录需要不同验证步骤。本轮尚未达到真实校准。

| 环节 | 可辨认修复轮次 | 主要工作 |
| --- | --- | --- |
| 创建几何 | 1 | 从独立 stage 建立外壳、平底管、直孔与底座；96 段管、128 段孔。 |
| USD 保存与重载 | 1 | 独立资产无外部引用；完整场景在新进程重载并复位三次。 |
| 碰撞建模 | 4 | 小尺寸整体凸包粗化、毫米局部尺度仍失真、分段构造修正、原生 Cylinder 查询偏差排除。 |
| 质量惯性及材质 | 1 | 明确质量惯性；读取夹指 tensor 回退材质，纠正未生效材质的解释。 |
| 操作点及坐标 | 1 | 固定 TCP 与孔座坐标；实测持握 Y 偏置补偿；检查夹指空间。 |
| 控制适配 | 3 | IK 容差、到底后平滑释放、GUI 入口参数修复。 |
| 独立判分 | 2 | 修正平口有限高度干涉度量；按实际连续时间计算稳定保持。 |
| 采集接口接入 | 1 | 复用 HDF5 和 MP4；明确 obs/action/next_obs；失败数据保留。 |
| 亚毫米条件调试 | 3 | 修正渲染隐式步进；同初态跨频率复核；无接触微动诊断。 |

人工分类活跃时间没有独立计时，各类调试交叠，不能给出可信的人时拆分。上表是可追溯的问题迭代数，不是互斥工单。自动重建实测：几何数组 0.00110 s；USD、碰撞、质量材质与保存 0.07085 s；独立重载和尺寸读取 0.00838 s。不能把这些执行耗时当作开发工时。

| 正式实验组 | 仿真时长 | 执行墙钟 | 含初始化墙钟 |
| --- | --- | --- | --- |
| 主扫描 | 27.81 min | 57.86 min | 59.91 min |
| 同初态复核 | 12.06 min | 26.54 min | 27.68 min |
| 单因素对照 | 2.89 min | 4.91 min | 5.17 min |

表中耗时来自逐轨迹日志，含初始化墙钟仍不包含最终序列化和合并，也不是整个项目投入。父进程计时另保存在原 process_timing.json。

下一步应先增加边界附近的姿态与持握扰动重复，定位 120 Hz 释放穿透和原生 Cylinder 查询偏差，再校准真实仪器尺寸、碰撞外形、摩擦、夹爪驱动与控制延迟。需要真机另行验证受阻力、滑移、材料与几何公差；本轮不模拟液体、玻璃破碎、软体或测量结果，也未开展训练。

## 复现调用与录像

当前机器使用现有 labutopia-env 的 Python 3.11、Isaac Sim 5.1.0.0 与 RTX 4090。以下命令在项目目录执行；输出目录必须使用新名称。GUI 主入口已实际成功运行，交互保持窗口的选项未额外人工测试。

```bash
cd /home/wujing/Desktop/vla/LabSim
bash demos/minimal_precision_insertion/run.sh --offsets 0 --keep-open
```

与其他任务一致的配置入口已验证：

```bash
../labutopia-env/bin/python main.py --config-name minimal_precision_insertion
```

顺序执行完整扫描：

```bash
bash demos/minimal_precision_insertion/run.sh --headless \
  --offsets 0,0.1,0.2,0.25,0.3,0.35,0.4,0.5,0.8 --repeats 3 \
  --physics-hz 120,240,480 \
  --output outputs/minimal_precision_insertion/my_scan
```

同初态比较、敏感性、微动、重载、离线重判分及绘图命令见随包 README.md 和项目 demos/minimal_precision_insertion/README.md。原始 HDF5、动作与物理 JSONL 留在工程 outputs/minimal_precision_insertion 中；data/raw_file_manifest.json 给出路径、大小及小文件哈希，报告包未复制全部大型原始记录。

成功录像作为文件对象嵌入本文；支持 OLE 的桌面 Word 可打开。当前 Linux 环境已验证嵌入字节一致及文档版式，未验证 Windows Word 双击交互。也可直接打开随包四段 MP4。

## 复现与原始证据

# 亚毫米偏差下的器皿插入

这是独立的纯仿真任务 `minimal_precision_insertion`。只使用 Franka、桌面、灯光、双视角相机、合成孔座及试管代理物，不引用 `lab_001`。任务和记录器已注册到现有工厂；`minimal_pick` 的代码和配置保持原样。这里没有训练、模型推理或真机操作。

## 启动与复现

在 `/home/wujing/Desktop/vla/LabSim` 中执行。`run.sh` 使用现有的 `../labutopia-env/bin/python`，默认显示 Isaac Sim GUI；每次输出目录必须是新的。

```bash
cd /home/wujing/Desktop/vla/LabSim
# GUI 中运行一次中心插入并保存 USD、RGB、HDF5、接触和结果
bash demos/minimal_precision_insertion/run.sh --offsets 0 --keep-open

# 与其他任务相同的 main.py 配置入口
../labutopia-env/bin/python main.py --config-name minimal_precision_insertion

# 主扫描；一个父进程按顺序启动三个 Isaac 子进程
bash demos/minimal_precision_insertion/run.sh --headless \
  --offsets 0,0.1,0.2,0.25,0.3,0.35,0.4,0.5,0.8 --repeats 3 \
  --physics-hz 120,240,480 --output outputs/minimal_precision_insertion/my_scan

# 用同一实测持握位姿与关节位置、零速度复核边界
# 所有位姿写入均在初始化，控制和判据与主扫描共用
../labutopia-env/bin/python demos/minimal_precision_insertion/matched_initial.py \
  --reference outputs/minimal_precision_insertion/my_scan/hz_120/physics_120/episode_0000_initial.json \
  --headless --offsets 0,0.3,0.35,0.4 --repeats 3 --physics-hz 120,240,480 \
  --output outputs/minimal_precision_insertion/my_matched_comparison

# 120 Hz 异常附近单项比较 contact offset、位置迭代和碰撞表示
../labutopia-env/bin/python demos/minimal_precision_insertion/sensitivity.py \
  --reference outputs/minimal_precision_insertion/my_scan/hz_120/physics_120/episode_0000_initial.json \
  --output outputs/minimal_precision_insertion/my_contact_diagnostics

# 无孔座接触的 0.1、0.5、1、2 mm 末端运动诊断
bash demos/minimal_precision_insertion/run.sh --headless --diagnostic \
  --physics-hz 120,240,480 --no-video \
  --output outputs/minimal_precision_insertion/my_free_motion

# 导出的完整场景在全新 PhysX 进程中重载并复位三次
../labutopia-env/bin/python demos/minimal_precision_insertion/validate_reload.py \
  outputs/minimal_precision_insertion/my_scan/hz_120/physics_120 \
  --headless --output outputs/minimal_precision_insertion/my_reload_check

# 离线重判分和时间对齐核查，不启动 Isaac 或占用 GPU
OPENBLAS_NUM_THREADS=1 ../labutopia-env/bin/python \
  demos/minimal_precision_insertion/audit.py \
  outputs/minimal_precision_insertion/my_scan --output /tmp/my_scan_audit.json

# CSV、JSON、结果图、深度图和注入偏差核查图
../labutopia-env/bin/python demos/minimal_precision_insertion/analyze.py \
  outputs/minimal_precision_insertion/my_scan --output /tmp/my_scan_analysis
```

程序打印 `SUCCESS`、`BLOCKED`、`PHYSICS_INVALID` 等实际任务状态。批次中存在失败结果不等于运行程序失败；配置错误或中心门槛失败会返回非零退出码。运行期间不应启动其他 Isaac 进程进行性能比较。

## 合成资产与有效尺寸

`geometry.py` 从零生成 `tube.usda` 和 `module.usda`，单位为米，Z 向上，无外部资产依赖。机器人来自 `assets/robots/Franka.usd`，控制器复用项目使用的 Lula IK 和关节位置目标接口。每组输出包含资产、配置及展开后的 `initial_scene.usda`。

- 试管：平底、不透明、刚性，外径 10.0 mm，长 50 mm，质量 0.02 kg，重心在中心。惯性采用实心圆柱公式，横向约 `4.2916667e-6`、轴向 `2.5e-7 kg m²`。
- 孔座：内径 10.6 mm，深 20 mm，外径 18 mm，平直入口，无倒角；18 × 18 × 4 mm 底座，固定碰撞体。孔口 Z=0.790 m，孔底 Z=0.770 m。
- 试管视觉是 96 边圆柱；碰撞是 96 个三角楔形凸体组成的动态刚体。每块有 6 个顶点，在 mm 局部坐标建模并显式缩放 0.001；避免微小尺度凸包烹制导致外轮廓粗化。孔壁是 128 段闭合的静态三角网格，`approximation=none`，不会填平孔。
- 相对理想圆的最大径向离散误差：试管约 2.677 µm、孔约 1.596 µm。读取全部试管凸体烹制顶点，并用 384 条径向、3 条竖直 PhysX 射线核查实际孔腔的采样尺寸。没有取得完整的孔壁烹制三角形，不能宣称完全排除所有烹制误差。
- 试管和孔座物理材质：静摩擦 0.5、动摩擦 0.4、恢复系数 0、average 组合。两侧 contact offset 都为 50 µm，rest offset 为 0。contact offset 是接触生成距离，不是位置精度。
- 默认 CPU PhysX、numpy、TGS、位置/速度迭代 32/8、CCD 开启。RTX 用于渲染。机械臂继承原 Franka 资产的驱动参数，实测值和材质绑定查询保存在 `effective_parameters.json`，需结合报告中的回退与校准限制解释。

PhysX tensor 的额外读取确认夹指回退材质为静摩擦 0.5、动摩擦 0.5、恢复系数 0；不能使用资产中未生效的 RubberGray 数值。运行时关节速度上限接近浮点上界，实际没有可用的机械臂速度限幅；本任务通过固定目标轨迹限制下降速度。该设置未经过真机校准。

这些尺寸与外观均为合成实验参数；资产有外观、可碰撞、可操作、可记录，尚未经过真实仪器或真机校准。

## 控制与判分

仅在初始化阶段设置机器人、试管和孔座状态。实验开始后，试管始终是动态刚体，由夹爪物理接触维持运动；没有绑定、运行中位姿写入或运动学试管。

目标 TCP 固定在 X=0.20 m、Y=0，孔座在初始化时沿 −X 平移名义偏差。孔座初始 Y=0.00030 m 是对原夹指持握偏置的仿真补偿，所有主扫描条件共用。实际底端偏差与倾角另行测量，不能用名义偏差代替。

时序固定为：0–2 s 夹持；2–24 s 以 1 mm/s 下降 22 mm，从孔口上方 2 mm 到孔底；25–27 s 平滑打开夹爪；27–30 s 上撤 40 mm；30 s 起稳定性检查。Lula 位置容差 10 µm，姿态容差 0.001 rad。无主动搜索、视觉纠偏或恢复。

物理频率 120、240、480 Hz 对应每个 60 Hz 控制周期 2、4、8 个显式物理步。渲染独立调用，不让渲染偷偷推进物理时间。每一步核对 Isaac 引擎时间；接触接口使用当前 `physics_dt` 将冲量换算成力。末帧可以因终止而包含较少物理步。

成功使用统一的实际状态判据：插入深度至少 18 mm 且不超过 20.05 mm；两夹指打开到 35 mm 以上；TCP 撤离孔口至少 35 mm，夹指接触力低于 0.01 N；试管在孔腔内；释放后位置变化小于 0.1 mm、姿态变化小于 0.5°，连续保持至少 1 s；整个过程中的几何重叠不超过固定的 50 µm 容差。

独立几何检查将实际烹制的试管顶点和棱边变换到世界坐标，裁剪到孔壁高度范围，再检查孔内多边形半平面以及底座侵入。平口边缘的有限高度重叠也纳入计算，不将整段横向干涉当作浅接触的穿透深度。另用完整的腔内约束防止“孔外但高度满足”被算作成功。算法适用于本实验靠近孔座、接近直立的状态；不等价于任意场景实体的精确全局穿透查询。`audit.py` 根据保存的实际姿态重算，独立于控制器和名义偏差。

`BLOCKED` 要求有孔座接触、深度不足、实际下降在约 2 s 内少于 0.1 mm，同时目标仍在下降。另有 `GRASP_SLIP`、`DROPPED`、`UNSTABLE_AFTER_RELEASE`、`TIMEOUT`、`PHYSICS_INVALID`、`CONTROL_OR_IK_FAILURE`，均按实际状态或执行异常判断。代码没有按偏差数值给成功或失败标签。

## 记录结构

复用 `MinimalPickCollector` 的流式 HDF5、双相机和 MP4 写入器。所有失败轨迹也保留；合并的 `episode_data.hdf5` 仅包含成功轨迹。视频 60 fps；每个控制步一条 obs/action/next_obs 转移；每个物理步一条接触与状态 JSONL。

每组保存 `config.yaml`、`effective_parameters.json`、`runtime_geometry_probe.json`、`tube_runtime_probe.json`、USD、`collision_debug.png`。每条轨迹保存初态、任务事件、碰撞烹制快照、结果、物理步记录、HDF5 和录像。运行目录保存提交信息、分支、源码哈希及实际源码副本。仿真时长、引擎时长、执行墙钟耗时、初始化耗时分开记录。

HDF5 包含 RGB、8 维既有动作格式、9 维实际关节位置、8 维 agent_pose/next_agent_pose、物体 7 维位姿及后继位姿、时间戳、目标/实际 TCP、IK 残差、偏差、倾角、深度、重叠、持握滑移、接触、done/reward。本轮只是物理实验与采集接入，没有运行 ACT、Diffusion 或 VLA 训练。

正式实验结果及尚未核实的部分见 `docs/experiments/minimal_precision_insertion_20261013.md`。同初态的三次重复用于检查重复性，不代表广泛场景成功概率。

## 已发现的几何限制

2026-10-13 的 USD Cylinder 对照在 PhysX 射线查询中出现约 0.100 mm 的边界偏差。尚不能区分查询膨胀与实际碰撞边界，因此这三条旧诊断记录保留但排除于精细边界比较。当前版本在插入前执行 384 条径向射线和 10 µm 尺寸门槛；不通过则记录 `geometry_gate_result.json` 并退出。`sensitivity.py` 将这种有明确证据的 Cylinder 拒绝记录为几何排除，其他运行错误仍返回失败。默认分段凸体通过了该检查；完整重载测得最大径向误差约 2.69 µm。

正式主扫描为 81 条，同实际初态复核 36 条，接触及迭代单因素对照 9 条；另完成 GUI 中心插入及 12 条无接触微动诊断。结果图和录像位于 `outputs/minimal_precision_insertion/analysis_primary_final` 与 `representatives_final`。报告包不会复制全部大型 HDF5 原始记录，原始路径与哈希索引另存于交付清单。
