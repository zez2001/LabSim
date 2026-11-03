# 单细胞测序 unit 场景

每个 unit 固定包含一台可操作仪器、Franka、任务目标和独立物理评分。使用源资产和既有接触模型，复用当前 `Project_release_v1` 的公开动作执行器、回执、GPT 工具与 π0.5 评测循环。代码基于上游 `ab519ed` 完成 rebase；旧实验不改写。这里验证 expert 数据生成与 policy 接口，不开展训练或完整 benchmark。

| unit ID | 仪器 | 简单任务 | 范围 |
| --- | --- | --- | --- |
| `ika_open` | IKA KS 4000 | 夹住把手开盖，松手撤离，保持至少 3 秒 | 双气弹簧为未标定的仿真补充；不加热、不混匀 |
| `diynafluor_uncap` | DIYNAFLUOR | 取遮光帽、放到原停放座、释放撤离 | 不插样品管，不输出浓度 |
| `flex_load` | Opentrons Flex | 将空 MagSep 架放到 D2 表面、释放撤离 | 架体为任务载荷；不移液，不代表官方耗材适配 |
| `magsep_transfer` | MagSep 空架 | 桌面抓取并搬到标记工位、释放撤离 | 独立场景不加载 Flex；不插管或模拟磁分离 |
| `pcr_insert` | CFX Opus 派生样品块 | 6 mm 小试管插入中央第 4 行、第 6 列孔、释放撤离 | 任务用真实孔腔和小管为工程模型；盖子预先打开，不代表厂家耗材兼容 |

注册表和目标文本集中在 [units.json](../../config/cell_units/units.json)。PCR 的原始资产仍是贴图孔；`pcr_insert` 单独生成派生孔腔及耗材，尺寸／动力学未标定，实际完成状态以独立评分为准。OpenFlexure 仍存在原夹爪干涉，不注册成功操作 unit。Poseidon 仅为辅助支架。其余三类未建成的整机仍保留原阻塞说明。

## 首次调用

沿用已有 Linux / Isaac Sim 5.1 / Python 3.11 / NVIDIA GPU 环境；使用现有 Conda，不在工程内建环境。大型资产按 [assets/README.md](../../assets/README.md) 获取，新增源资产默认位于 `local_assets/`。Franka 和最小烧杯是原项目基础依赖。单 GPU 顺序运行仿真。

```bash
export LABSIM_PYTHON=/absolute/path/to/existing/isaac-python
./labsim unit list
./labsim unit demo --unit ika_open --headless --output outputs/ika_demo_NEW --dry-run
./labsim unit collect --unit ika_open --headless --output outputs/ika_expert_NEW
./labsim unit dataset-check --path outputs/ika_expert_NEW/episode_0000
```

将 `--unit` 替换为表内 ID 即可运行其他仪器。省略 `--headless` 打开 GUI。`demo/collect/eval` 支持 `--episodes 1..20`，在同一进程顺序 reset。输出必须为新目录，不覆盖已关闭 episode。`--cache` 指定已有新增仪器缓存。

`teacher` 复用原接触演示的连续 IK 路径，仅通过关节驱动操纵物体，不绑定载荷或在运行中写载荷位姿。任务只截取明确的简单目标，不要求每次跑完整设备循环。评分基于实际接触、物体/罩盖状态、真实松爪撤离和稳定时间，与 teacher 阶段名和模型声明无关。

## GPT-6 图像闭环

默认原比色皿 Cubence 入口保持原配置。unit 允许使用接手者明确指定的 HTTPS Responses 服务，固定模型 `gpt-6-astra`，凭据只从 `LABSIM_UNIT_API_KEY` 环境变量读取。`--provider-config` 是不含密钥的 JSON；可从 [提供方配置示例](../../config/cell_units/gpt_provider.example.json) 复制后填写服务地址。不要将密钥写入仓库、命令参数或结果。

```bash
read -rsp 'API key: ' LABSIM_UNIT_API_KEY
export LABSIM_UNIT_API_KEY
./labsim unit eval --unit diynafluor_uncap --backend gpt6 --headless \
  --provider-config /absolute/path/to/provider.json --max-calls 8 \
  --budget-ledger /absolute/path/to/shared-budget.json --output outputs/cap_gpt_NEW
unset LABSIM_UNIT_API_KEY
```

使用同一预算账本累积探针和重跑开销，最多 $30 的沿用价格估算和 1500 次请求；该估算不是自定义服务账单。GPT 只读取同步 RGB、相机标定、机械臂状态、指端接触和目标文本；不获取器材真值、teacher 路径或评分内部状态。模型等待期间物理暂停，通用动作由当前 release facade 限幅和执行。8 次调用用于短程功能验证，不能据此声称任务成功或成功率。

## π0.5 验证

使用独立、已有 Isaac 与 OpenPI 依赖的本机 Python；本机部署记录在 `local_setup/cell_units/`。原 `labsim` 环境保持原样。依赖来自固定 [RLinf/openpi](https://github.com/RLinf/openpi/tree/c5dc4b9296a1a4739bf52828f28a579f12dce763)，模型为 [RLinf-Pi05-LIBERO-130-fullshot-SFT](https://huggingface.co/RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT/tree/6222623f635769bfc73c9472e29fab9b7fd8e027)。下载 `model.safetensors` 和 `physical-intelligence/libero/norm_stats.json` 即可，不下载优化器或训练数据。

```bash
export LABSIM_PYTHON=/absolute/path/to/existing/policy-isaac-python
export OPENPI_DATA_HOME=/absolute/path/to/openpi-cache
./labsim unit eval --unit flex_load --backend pi05 --headless \
  --checkpoint /absolute/path/to/RLinf-Pi05-LIBERO-130-fullshot-SFT \
  --max-calls 120 --max-actions 600 --output outputs/flex_pi05_NEW
```

原权重及归一化 SHA256 在运行前核验，复用原 `Pi05LiberoAdapter` 的机器人坐标转换、夹爪符号和动作限幅。模型动作 20 Hz、普通 unit 物理/执行 120 Hz（PCR 为 480 Hz），每个模型动作执行 6 步（PCR 为 24 步）；每轴平移上限 0.5 mm、旋转 0.004 rad。使用官方 LIBERO 变换、量化归一化、双 RGB、10 步去噪；关闭编译加速进行小规模验证。LIBERO 权重未针对 LabSim 微调，接通动作不等于学会仪器任务。默认最多 120 次推理、600 个动作，即 30 秒仿真；碰撞或动作不可达会提前停止。

### 微位移控制修正与验证边界

早期 1 秒录像只明显动夹爪是一个实际控制问题：策略每轴位移限幅 0.5 mm，而 Lula 默认位置容差 1 mm，导致求解器接受未变化的关节热启动。旧回执的 `target_reached` 不能作为机械臂移动证据。

当前 `kinematics.py` 使用有界局部 IK，以实际 FK 计算误差，位置门槛 0.01 mm、角度门槛 0.0001 rad，保持每个物理步的关节限位和速度约束。绝对差分避免零位关节的数值导数消失。π0.5 摘要另记录真实末端路径、最大位移和是否超过 0.1 mm；`integration_complete` 同时要求动作执行和实际机械臂移动，任务成功仍由物体状态独立判定。

### 已抓住空架的放置评测

针对 Flex／MagSep，可用 `--initial-state placement-ready` 从明确的放置初态开始。expert 先通过真实接触抓取空架并搬到目标上方约 6 cm；模型随后负责下放、支承后松爪、撤离和稳定。初始化单独保存到 `episode_0000/initialization/`，不计入 policy 时长、模型调用或成功能力。主 MP4 仅包含模型控制段，不拼接为端到端 π0.5 成功演示。

```bash
./labsim unit eval --unit magsep_transfer --backend pi05 --initial-state placement-ready \
  --checkpoint /absolute/path/to/RLinf-Pi05-LIBERO-130-fullshot-SFT --headless \
  --max-calls 120 --max-actions 600 --output outputs/magsep_placement_NEW
```

同一参数适用于 `flex_load`，也可用于 GPT 或 `serve`。不支持其他 unit 或 expert `collect`。判分要求先形成目标支承再松爪，不能从空中丢下、落到目标后算成功。碰撞仍立即终止。原默认初态继续保留，用于完整抓取放置目标的评测；两种初态不可混算成功率。

### PCR 派生场景

`config/cell_units/pcr_insert.json` 集中记录所有尺寸与假设。沿用源外壳与滑盖，在本次派生 USD 中将贴图孔／实心块换为有底、有侧壁的 12×8 孔阵列，并切除该区域内相冲突的旧壳面与碰撞盒；原缓存不改写。小管外径 6 mm、总高 26 mm、盖径 8 mm，目标孔深 12.6 mm，位于第 4 行第 6 列（配置零基索引 3/5）。选择中央孔是为了给原装夹指留出与外壳／导轨的空间。以上是任务用仿真配合尺寸，未经厂家或实物确认。

PCR 使用 480 Hz 物理、每指 0.5 N 驱动力上限，expert 在入孔阶段使用物体位姿反馈对齐；policy 没有该反馈。Franka 使用原夹指、缓慢闭合和限力夹持，无附着关节、无运行中管子位姿写入。评分检查真实双指夹持、抬升、目标孔横向误差小于 0.6 mm、插入至少 10 mm、孔底支承、松爪撤离及 3 秒稳定。`collect --unit pcr_insert` 可生成数据，`eval` 和 RPC 沿用同一入口；原静态 `load_asset('biorad_cfxopus')` 不会自动变成派生孔腔版。

## Python 与外部策略接口

在启动 `SimulationApp` 之后：

```python
from demos.cell_units.environment import UnitTask
from demos.lab_cuvette_project_release_v1.environment import ProjectEnvironment

task = UnitTask('ika_open', 'outputs/python_NEW', backend='external')
env = ProjectEnvironment(task)
obs = env.reset()
receipt = env.execute({
    'episode_id': obs['episode_id'], 'observation_id': obs['observation_id'],
    'action_id': 'wait-001', 'type': 'ee_delta', 'frame': 'world',
    'values': [0.] * 6, 'duration_s': .05,
})
env.finish('POLICY_BUDGET')
env.close()
```

公开方法沿用 `reset / observe / execute / receipt / status / finish / close`。动作支持 `ee_pose`（world xyz 米 + wxyz）、`ee_delta`（平移米 + rotvec 弧度）、`joint_position / joint_velocity`；夹爪参数为双指总开口米与每指力上限 N。policy 每次最多 3 秒、0.04 m、0.15 rad，速度上限 0.02 m/s / 0.15 rad/s。动作回执的 `target_reached` 只表示 TCP 到位，不代表任务成功。重复 action ID 返回原回执，旧 episode / observation 不能控制新场景。

`./labsim unit serve --unit ika_open --headless --output outputs/rpc_NEW --port 8097` 提供与当前 release 相同的 loopback `POST /call` RPC（`project.*` 与 `env.*`）。`serve` 由外部客户端推理，即使传入 `--backend pi05` 也不会加载本地权重；该参数不选择服务端控制器。无 teacher/debug RPC。通过 `env.reset` 初始化，通过 `shutdown` 正常结束。端口只监听本机，不暴露到公网。

## 输出与数据含义

每个 `episode_0000/` 保存 `scene_contract.json`、原始资产导入和计划、双视角 MP4、`episode.h5`、无损压缩的逐物理步轨迹、独立评分和 `complete.json`。GPT/π0.5 另保存真实输入、原始输出、动作回执及预算/调用统计。`worker_status.json` 记录任务与数据关闭状态，外层 launcher 的 `process_exit.json` 记录子进程真实退出码。使用 Isaac 官方 `fast_shutdown`；不声称完整原生扩展清理通过。异常或缺失完成状态均返回非零，不能用 Isaac 快速退出的 0 覆盖任务异常。

当前场景版本为 `SingleCellUnit_v2`、评分版本为 `SingleCellUnitScore_v2`。H5 保持独立 unit 布局，读取器兼容历史 `SingleCellUnit_v1` 和当前 v2，不伪装为原比色皿数据：

- `observations/*` 保存 N+1 个时间、9 维关节位置/速度、TCP 和两路 256×256 RGB；侧视固定，腕视实际随手移动。
- `actions/joint_targets` 为 N×stride×9，stride=物理 Hz/30：普通 unit 为 4，PCR 为 16。保存图像间隔内真正施加的关节目标；`physics_count` 标记有效数量，最后不足 stride 的补零不执行。
- 图像通常 30 Hz，最后部分区间保留真实时长；模型公开控制时钟为整数步/物理 Hz，原生 PhysX 浮点时钟另保留在逐步轨迹中。
- 文件关闭后才标记 `closed`；`dataset-check` 验证前后时刻、动作终点时间、块形状和全部动作有限值，并提供普通 batch 回读；不再只抽查前 8 个动作块。成功 expert 与失败 policy 保留各自标签，不能混作成功示范。

这是可复现的功能验证数据，不包含 ACT/DP 训练接入或训练结果。当前实测汇总与视频见 [unit 交接](../../docs/cell_assets/单细胞Unit验证.md) 和唯一最终 HTML 内的对应资产卡片。

## 代码规范与版本范围

命名、职责划分、参数说明、异常定位和文档一致性遵循任务说明中的 Google code style 与黄山版手册适用于 Python 的规则；不套用 Java 的驼峰、包结构或禁止私有下划线等语言专用规则。保留外部参数、结果防覆盖和物理安全边界，不在高频内部循环叠加重复校验。

几何参数位于 `config/cell_units/`；独立评分阈值集中在 `scorer.py`，以单位后缀命名。v2 要求开盖后整个 3 秒窗口都已撤离；PCR 插深同时要求目标孔 XY 对准及合理孔深，源托架中的小管不能单项标作已插入 PCR。历史记录仍按其原始版本呈现；重评分单独记录，不改写原标签或源码指纹。

公开入口缺少 `--path`／`--checkpoint` 或动作预算非正时，在启动 GPU 前报错。初始化未完成的 H5 保持 `closed=false`，不会生成完成标记；异常不被快速退出包装成成功。复核范围与结果见 [代码复核](../../docs/cell_assets/代码复核.md)。
