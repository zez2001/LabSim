# LabSim 开发接入指南

本指南面向接手开发和复现实验的工程师。正式入口为根目录 `./labsim`，当前支持的完整器皿任务为 `Size_v1 / standard`。历史版本可以复查，不作为新代码的默认入口。项目治理及提交要求见[贡献规则](../../CONTRIBUTING.md)。

## 1. 接手时先区分四类交付物

- **代码与配置**：当前 `codex/labsim` 分支，保留完整提交历史；`main` 为上游基准。
- **资产**：Git / Git LFS 管理的 USD、派生配置和来源清单。clone 后必须取得实体，不能把 LFS 指针当资产。
- **结果证据**：`docs/lab_cuvette_loading/Size_v1/` 下的报告、逐集审计和代表录像，可直接阅读。
- **完整数据与运行环境**：本机 `outputs/`、同级 `labutopia-env` 及其他运行依赖。它们不因 clone 自动出现，须另行传输或重建。

首次接手记录 `git rev-parse HEAD`、`git status --short`、解释器路径、`./labsim doctor --json` 输出。不要在未知工作区执行 reset、clean 或覆盖已存在的输出。所有示例中的 `outputs/...` 是新目录占位名；每次实际调用换成唯一目录。

## 2. 当前电脑：复用已经验证的环境

仓库原本位于 `/home/wujing/Desktop/vla/LabSim`，解释器为项目同级的 `../labutopia-env/bin/python`。入口从仓库位置解析路径，不要求从特定工作目录调用：

```bash
cd /path/to/LabSim
./labsim doctor
./labsim demo --output outputs/lab_cuvette_loading/Size_v1/demo_onboarding_001 --dry-run
./labsim demo --output outputs/lab_cuvette_loading/Size_v1/demo_onboarding_001
```

默认 GUI；无显示器的运行显式加 `--headless`。不要同时启动第二个 Isaac 进程。现有 GPU 锁会串行化使用该锁的任务，不能代替检查其他不受锁控制的进程。新 demo 也仍须检查实际独立评分，不能仅检查退出码。

## 3. 新机器：部署状态与迁移关口

已验证软件基线为 Python 3.11、Isaac Sim 5.1、Linux 和 RTX 4090。上游声明的安装步骤见[上游 README](../upstream/README.labutopia.md)，仓库普通 Python 依赖见 [requirements.txt](../../requirements.txt)。它是开发依赖清单，不是完整可重建的系统镜像或跨平台锁文件。

新机器建议按以下顺序接入：

1. clone `codex/labsim`，安装 Git LFS 并拉取资产实体；保留所用提交。
2. 建立 Python 3.11 / Isaac Sim 5.1 环境；安装项目依赖，并按 NVIDIA 对当前机器的要求准备驱动和显示环境。不要用“pip 安装完成”替代仿真可用性检查。
3. 通过 `LABSIM_PYTHON` 选择该环境，运行 `./labsim doctor --json`。读取返回的错误和警告，先解决丢失资产、模块、环境目录和冻结文件错误。
4. 检查遗留路径依赖。`demos/lab_cuvette_external/usd_python.sh` 仍引用同级 `labutopia-env` 下特定 USD / PhysX 扩展目录；冻结场景也包含既有几何工具环境路径。仅设置 `LABSIM_PYTHON` 不保证这些路径全部可迁移。
5. 在新输出目录做资产加载和一次完整 GUI / headless demo，核对尺寸、相机、物理参数、release / retreat / 稳定结果，再采集数据。

`doctor` 是 CPU 预检：不启动 Isaac、不开窗口、不测试真实接触。当前交接没有把新机器部署列为实际完成。若需修正绝对路径或兼容新的 Isaac 版本，应独立记录迁移变更及环境验证；被实验冻结的文件改变后，要建立新冻结版本并重新取得资格，不能直接沿用旧指纹和成功标签。

## 4. 正式任务的边界与配置

- 入口配置：[standard.yaml](../../config/lab_cuvette_loading/Size_v1/standard.yaml)。冻结清单：[frozen_scene.json](../../config/lab_cuvette_loading/Size_v1/frozen_scene.json)，覆盖 75 项依赖。
- 资产注册：[registry.json](../../assets/lab_cuvette_loading/Size_v1/registry.json)，正式选择 `cuvette_xy_1000`；尺寸 10×10×67.5 mm，20 g 质量假设。
- 来源为完整 6×6 参数化架，A1 操作槽、F6 蓝色器皿；16 mm 方槽为工程假设。当前只有一台目标仪器。
- 目标为原 A 座 `candidate_far_hinge`。仪器装配和座的源几何、碰撞与物理参数不因尺寸实验修改。
- 物理 240 Hz、控制 60 Hz、CPU PhysX；控制使用真实器皿位姿。质量、摩擦及接触参数不代表真实标定。
- 成功需要实际清槽、抓持搬运、装载、支撑交接、双指释放、机械臂撤离和 3 秒稳定；预插入或保持夹持不算完整成功。
- collect、train、训练内自动验证保持 standard，禁止悄然启用资产、布局、光照或物理随机化；训练 RNG seed 独立配置。

## 5. 代码地图与修改边界

先从这些位置追踪实际调用，避免另写一套环境或采集器：

- `labsim` → `scripts/labsim_cli.py`：稳定 CLI、路径和覆盖保护；不替代底层物理实现。
- `demos/lab_cuvette_size_v1/run.py`、`asset_selection.py`：正式组合入口、注册资产选择与配置解析。
- `tasks/lab_cuvette_loading_env_v1.py`：既有环境接口、机器人状态及实际动作执行；Size_v1 在此基础上组合。
- `controllers/lab_cuvette_env_v1_controller.py::LabCuvetteTeacher`：完整示范状态机、接触锁存与分阶段卸载；`demos/lab_cuvette_env_v1/` 提供场景、相机和物理采样。锁存持续施加夹指目标，不建立物体固定约束。
- `scripts/collect_lab_cuvette_size_v1_standard.py`：真实子进程、verify5 门控、采集阶段及退出证据。
- `scripts/validate_lab_cuvette_size_v1_data.py`：正式准入、实际事件验证、索引与正常读取校验。
- `policy/dataset/minimal_pick_dataset.py`：沿用的正常 ACT / DP 数据入口；成功和失败过滤在源标签基础上执行。
- `demos/lab_cuvette_size_v1/build_assets.py`、`scan_family.py`、`geometry_audit.py`：尺寸派生、几何筛选及证据范围。

这些路径中部分属于冻结依赖，**列出来是为了读懂，不表示可以原地改写而继续使用旧实验资格**。修改前查看冻结清单及 `git diff`。原始附件、原 CAD、历史 USD、旧结果和旧标签保持原样；新任务用版本化配置、派生资产和独立输出。

策略对接沿用 `tasks.lab_cuvette_loading_env_v1.LabCuvetteLoadingEnvV1`。`SimulationApp` 由 launcher 创建，不能在普通 Python 中跳过 Isaac 初始化直接实例化环境：

- `reset(seed=None, options=None)` 返回 `(observation, info)`，完整记录初始化和自然落稳；不会自动调用 teacher。
- `step(action)` 返回 `(observation, reward, terminated, truncated, info)`；`chunk_step(actions)` 顺序执行动作块。
- 动作必须是带 `episode_id`、`observation_step`、`type` 和 `values` 的字典；过期 episode / 观测动作会被拒绝。`joint_position`、`joint_velocity`、`ee_pose`、`ee_delta` 的单位、参考系和夹爪语义见类内 `ACTION_SPECS`；不能直接发送无类型数组。
- `get_observation()`、`render_camera(name)`、`get_camera_meta(name)` 提供公开观测 / 图像 / 标定元数据；器皿真值与碰撞诊断属于独立 debug / 记录通道。`close()` 结束环境和记录。

已有 RPC / 策略适配入口见 [Env_v1 接口文档](../lab_cuvette_loading/Env_v1/README.md)。接入新策略时首先复用同步 API，明确动作时序与真值使用范围，避免为同一任务另起一套采集格式。

## 6. 采集、审计与正常读取

完整命令和阶段说明见[项目主页](../../README.md)与[Size_v1 低层命令](../../demos/lab_cuvette_size_v1/README.md)。一个新 collection 的调用顺序为：

```bash
./labsim collect --phase verify5 --collection outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001 --headless
# 真实 5/5 通过后，再运行以下两个阶段
./labsim collect --phase success --collection outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001 \
  --allow-after-verified-five --headless
./labsim collect --phase controlled_failure --collection outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001 \
  --allow-after-verified-five --headless
./labsim validate --collection outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001 \
  --index outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001/dataset/episode_data.hdf5 \
  --output outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001/audit/collection.json
./labsim dataset-check \
  --index outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001/dataset/episode_data.hdf5 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Size_v1/collection_onboarding_001/audit/success_read.json
```

采集可耗费数小时；不要为快速看接口而复用正式配额目录。所有实际子进程必须闭合再扫描或索引 HDF5。阶段驱动退出 2 可能表示配额尚未补满，须结合保存的子进程退出码判断，不能自动把正常 quota 状态当仿真故障，也不能把非零仿真退出写成成功。

正式准入会排除几何预检、初始化错误、服务错误、人工中断和短预算诊断。受控失败必须有实际 INSERT 事件，其时间和深度与 H5 后继状态相符；只在配置声明偏差不能算有效失败。源数据标签不改写。

正常索引固定名为 `episode_data.hdf5`。collection 内采用相对链接，移动索引时需一并移动 collection；单集 H5 本身可以无外链。已有完整 collection 约 61 GB，单集便携样例约 1.96 GB，均不放入精简阅读包。git clone 仅得到小型审计和代表媒体。数据获取方式由交接方另行安排。

## 7. 观测、动作和标签语义

正常模型数据包含两路 `side_camera_rgb` / `wrist_camera_rgb` 与机器人 `agent_pose`；ACT / DP 正常读取动作宽度为 8：7 个臂关节位置目标加 1 个对称夹指位置命令。原始记录还保存实际双指的完整 9 维位置目标、真实状态和逐步力限制，不应把 8 维政策动作误解为末端笛卡尔增量。

环境按控制前观测、当前动作、物理执行后继状态对齐；原始时间戳、相机渲染时间和控制周期分别保留。240 Hz 接触与 60 Hz 控制的采样率不同。夹爪力上限由阶段调度，正式 transport 为每指关节 8 N 上限，不能当作双指总实测接触力。

至少保留 `record_valid`、`task_success`、`task_type`、`failure_type`、`termination_reason`、`condition_group`、`asset_id`、场景 / 控制 / 代码版本。成功 BC 默认只读取合格成功。受控提前停属于 `task_success=false` 的动作偏差组，不是自然失败；训练与验证按完整 episode 划分，不能把相邻帧拆到两边。

撤离前终止时，`post_retreat_window=unavailable`、撤离后稳定结果为 null；中止前末段另记为 `terminal_window`。缺失测量用 unavailable / null，不补 0。原生速度与位姿差分两种信号及质量告警保留。

## 8. 测试与交付

先用 `--dry-run` 检查新命令、显式输出和路径，再运行相关 CPU 测试；涉及环境、控制、碰撞、判分或相机的改变，必须补做对应真实仿真检查。CPU mock 或配置合成不能写成 GPU 运行成功。本轮统一 CLI 的验证范围以本次提交记录为准，不把新包装入口的 CPU 检查冒称再次采集 40 条。

需要模型训练时，沿用 `train.py` 和现有 Size_v1 ACT / DP 配置，详细 override 见[任务说明](../../demos/lab_cuvette_size_v1/README.md)。尤其 ACT 要使用新的两路相机名称。接手指南不自动启动训练，现有 40 条验证也不表示策略训练或物理闭环评测完成。

每次交付应包含变化目的、兼容性影响、确实执行的检查、已知限制及复现命令。完成验证后提交和推送，核对远端 SHA，再按[结果阅读包规范](../agent_handoff/README.md)建立新的小型交接包。报告、视频、CSV 和配置引用必须在包内可解析；完整数据单独管理。分支、标签与发布规则见[贡献规范](../../CONTRIBUTING.md)。

## 9. 当前已知限制和下一步建议

最优先的独立工作是新机器迁移验证、真实尺寸 / 质量 / 材料校准、速度信号差异定位及静态座实际碰撞读回。10.0 与 10.3 mm 的完整成功是离散配置结果，不是连续可用区间证明；最大 10.70 mm 几何证书不能当物理接触精度。

原 12.5 mm 资产和原座配套仍保留原结论。现有来源架及尺寸变体不是经过真实计量校准的数字孪生。后续进行 random 或 policy 物理评测须显式配置并单独报告，不应悄悄改变当前 standard 数据范围。
