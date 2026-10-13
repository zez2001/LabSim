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
