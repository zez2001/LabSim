# LabSim 开发接入

默认任务为 **`lab_cuvette_loading / Project_v1 / standard`**，稳定命令入口是仓库根目录 `./labsim`。历史 Size_v1 的资产、冻结配置、40 条数据和原始标签保持原样。项目治理见 [CONTRIBUTING.md](../../CONTRIBUTING.md)，日常开发继续使用 `codex/labsim`。

## 准备环境与资产

先记录提交、工作区和所用解释器：

```bash
git rev-parse HEAD
git status --short
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
export LABSIM_GEOMETRY_SITE=/absolute/path/to/isolated/geometry/lib/python3.11/site-packages
./labsim assets download
./labsim doctor --json
```

`LABSIM_PYTHON` 必须是已经安装 Isaac Sim 5.1 的 Python 3.11，具备本项目使用的 numpy、scipy、omegaconf、h5py、opencv、trimesh、rtree 等依赖；数据读取还使用 Torch。不要向已有 Isaac 或模型环境批量安装或升级 `requirements.txt` 来试错。新机器须先按 Isaac Sim 的安装要求准备 NVIDIA 驱动、GPU 和显示环境，再执行真实仿真验收。

几何审计使用 Shapely 的约束三角化接口，要求 Shapely>=2.1。可以复用已有的独立几何环境。如果尚未准备，以下命令只新建工具环境：

```bash
"$LABSIM_PYTHON" -m venv "$HOME/.local/share/labsim/geometry"
"$HOME/.local/share/labsim/geometry/bin/python" -m pip install --no-deps "shapely==2.2.0"
export LABSIM_GEOMETRY_SITE="$HOME/.local/share/labsim/geometry/lib/python3.11/site-packages"
```

这些命令不安装 Isaac，不修改原解释器中的包。几何目录还可以由 `LABSIM_GEOMETRY_SITE` 显式选择；默认位置即上述新环境。USD / PhysX 扩展从 `LABSIM_PYTHON` 对应的 Isaac distribution 中发现，不再通过旧版本脚本猜测开发者目录。旧 `demos/lab_cuvette_external/usd_python.sh` 只为历史版本保留。

[资产锁文件](../../config/lab_cuvette_loading/Project_v1/assets.lock.json) 固定 HF revision、各文件大小、SHA 和授权来源。`assets download` 自动匿名下载 82 个 HF 文件及固定来源的 Franka；不需要先登录 HF。完成的默认缓存会被 `doctor`、资产查询及任务入口自动采用。需要独立安装目录时：

```bash
./labsim assets install --asset-root /absolute/path/to/new_asset_tree
export LABSIM_ASSET_ROOT=/absolute/path/to/new_asset_tree
./labsim assets check --asset-root "$LABSIM_ASSET_ROOT"
```

完整目录保持 `assets/...` 层级。安装器拒绝覆盖不同内容；便携发布只清理 USD 文档字符串中的旧路径，保存原 SHA 与新 SHA，对比证据见 [portable_usd_semantics.json](../lab_cuvette_loading/Project_v1/assets/portable_usd_semantics.json)。源资产不回写。若修改默认缓存位置，设置 `LABSIM_ASSET_CACHE`；离线复用可执行 `./labsim assets download --offline`。

`doctor` 是 CPU 预检，不创建 SimulationApp，不证明物理任务或新机器部署已成功。实际部署必须使用新的输出目录完成一次 GUI、一次 headless、连续 reset 和数据读取，分别保存证据。

## 最小验收与数据读取

完整命令见[主页](../../README.md)。新输出目录不能已经存在；不要把失败尝试覆盖成后来的成功。先运行一条完整示范，再重复：

```bash
./labsim demo --backend teacher --scene standard --gui \
  --output outputs/lab_cuvette_loading/Project_v1/onboarding_gui_001
./labsim eval --backend teacher --scene standard --episodes 5 --headless \
  --output outputs/lab_cuvette_loading/Project_v1/onboarding_teacher5_001
./labsim collect --backend teacher --scene standard --headless \
  --output outputs/lab_cuvette_loading/Project_v1/onboarding_collect_001
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_v1/onboarding_collect_001/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_v1/onboarding_collect_001/read.json
```

仿真时长与墙钟耗时分别记录。进程退出 0 不代表任务成功，检查逐集 `result.json`、独立评分与连续视频。读取入口接受 standalone H5、正常 `episode_data.hdf5` 索引或单集目录；索引若有相对外链，须保留对应 collection。等待采集进程完全退出后再检查 HDF5。

合格成功需实际抓取、清槽、搬运、插入、承托、双指脱离、撤离及至少 3 秒稳定。撤离前结束时，`post_retreat_window.status=unavailable`，`stable_after_retreat=null`；最后的中止前窗口另记为 `terminal_window`。不要补零代替未测量值。

`collect --controlled-stop-depth-mm 5` 是 standard 场景中的明确动作偏差组；轨迹必须真正执行到 INSERT 才能作为有效任务失败。几何预检阻塞、初始化/服务错误、中断和短预算诊断单独归档，不能填充失败配额。成功 BC 默认只读合格成功；失败标签不为读取器而修改。

上游 `main.py` 也登记了独立配置名，并转入同一 launcher：

```bash
"$LABSIM_PYTHON" main.py --config-name lab_cuvette_project_v1 \
  --policy-backend teacher --headless \
  --output outputs/lab_cuvette_loading/Project_v1/native_main_001
```

这里 `--backend numpy` 仍是物理后端，`--policy-backend` 才是控制策略；旧实验的参数含义不变。

## 实现地图

- `labsim` → `scripts/labsim_cli.py`：项目命令、路径与防覆盖检查；历史配额命令保持显式入口。
- `demos/lab_cuvette_project_v1/run.py`：唯一 Project_v1 launcher，创建 SimulationApp、持有 GPU 锁，顺序运行 teacher / GPT，或启动本地 RPC。
- `factories/task_factory.py` 的 `lab_cuvette_project_v1` → `tasks/lab_cuvette_loading_project_v1.py`：原生任务注册，复用既有环境的场景、控制步进、相机、记录器与判分。
- `demos/lab_cuvette_project_v1/environment.py::ProjectEnvironment`：公开生命周期、动作限幅、插值、观测时效检查和幂等回执，不暴露 teacher 宏或 debug。
- `controllers/lab_cuvette_env_v1_controller.py::LabCuvetteTeacher`：使用器皿真值的专家；接触锁存与卸载只是机器人命令，没有物体固定约束。
- `demos/lab_cuvette_project_v1/scorer.py`：复用 Size_v1 的独立物理判据，另存 Project_v1 版本标签。`contract.py` 绑定标准场景、代码和实际资产 SHA，路径用逻辑 ID 归一化。
- `demos/lab_cuvette_project_v1/assets.py`、`runtime.py`：匿名资产获取、校验及所选运行环境发现。
- `data_collectors/lab_cuvette_env_v1_collector.py`：共享流式 H5 记录器，保留观测、动作、后继状态、控制辅助信号和独立结果。
- `policy/backends/cubence.py`、`cubence_tools.py`：独立提供方、预算、通用工具和图像闭环；`rpc.py` 是可选策略的公开适配。
- `policy/dataset/lab_cuvette_project_v1_dataset.py`：在正常 episode 读取器上检查 Project_v1、standard、完整任务和统一指纹。

相关正式配置位于 [config/lab_cuvette_loading/Project_v1](../../config/lab_cuvette_loading/Project_v1/)。当前固定选择 `cuvette_xy_1000`，原 A 座保持不变。35 个尺寸资产可查询并供独立实验选择；改变正式任务资产时同时更新几何、质量属性、控制引用及场景版本，不能仅改一个显示数字后继承成功资格。

## 策略接口与时序

公开 facade 支持 `reset / observe / execute / receipt / status / finish / close`。`observe` 包含 episode / observation ID、仿真时间、两路 RGB、关节位置和速度、TCP 位姿、夹爪开口及力限制、允许的双指接触信号、相机标定和任务文本。器皿真值、实际插入深度和评分内部状态留在 teacher / evaluator / privileged 记录通道。

动作必须包含 `action_id`、`episode_id`、`observation_id`、`type`、`values`、`duration_s`。支持明确的关节位置/速度与末端 `ee_pose / ee_delta`：米、弧度、world / TCP 参考系，四元数 wxyz，夹爪为双指总开口米；实际执行时转换成两个对称夹指位置。每次末端动作最多 4 cm / 0.15 rad / 3 秒，平移速度最多 0.02 m/s，还需满足控制周期整倍数、关节及 IK 限制。

GPT 的工具只有观察、通用末端移动、夹爪、有限步进和结束请求。模型网络请求期间仿真暂停，执行完整验证后的有界动作才推进物理。过期观测拒绝；已有动作 ID 先查询 receipt，部分执行异常也保留回执，不因超时重复运动。`finish` 只请求独立判分，不接收模型自填的成功标签。

ACT / DP 正常数据动作宽度为 8：7 个臂关节绝对位置目标和左指位置；完整 9 维实际命令、原始动作、后继状态和逐步每指力上限另存。它们不能当成末端增量。观测在动作前，后继状态在明确物理步后；240 Hz 接触与 60 Hz 控制分别保留时间。8 N 是每指关节力限制，不是双指实测总力。

[ACT 正式配置](../../policy/config/train_lab_cuvette_project_v1_act.yaml) 和 [DP task 配置](../../policy/config/task/lab_cuvette_project_v1_dp.yaml) 使用 `side_camera_rgb / wrist_camera_rgb`。读取器检查每集的 `record_valid`、独立成功资格、场景版本/指纹、asset / slot / seat ID 和 condition group；训练与验证按完整 episode 划分，均保持 standard。训练 RNG 种子与场景随机化是两个独立设置。本轮不执行模型训练。

## Provider 与可选模型

Cubence 只从当前进程的 `CUBENCE_API_KEY` 读取密钥，不写全局 Codex 配置。配置固定为 `gpt-6-astra`，预算默认估算 $30 / 1500 次网络请求；探针、重试与正式评测共用一个 ledger。密钥不得放入 Git、README、配置、日志、HF 或阅读包。完整 GPT 与 teacher 结果使用同一独立评分；API 连通、短动作或预插入通过不能当作完整任务成功。

π0.5 / RPent Harness 的部署路径、原模型哈希、有限预算与执行边界见[可选策略说明](../../policy/backends/OPTIONAL_POLICIES.md)。它们通过 `./labsim serve` 复用相同 facade，依赖显式选择既有部署，不自动安装或升级模型环境。新的任务级物理结果与历史 0.25 秒连通性记录分别报告。

## 修改、验证与交接

旧 V0 / ext / demo / Env_v1 / Size_v1 源文件、USD、冻结结果与标签保持原样。改动几何、物理、控制、评分或相机需要新的配置/数据指纹，并补相应真实仿真验证；路径适配与文档不能冒称重新采集历史 40 集。CPU 契约测试及所需轻量依赖见[工作流](../../.github/workflows/cpu-contracts.yml)与 [requirements/ci.txt](../../requirements/ci.txt)，请装入独立测试环境。

原生速度与位姿差分、输入几何与有效烹饪碰撞的差异继续保留。当前任务不是实物计量或真机精度认证；10 mm 任务完成不能改写原 12.5 mm 配套结论。更换资产、任意扩大孔径或放宽判分须单独说明，不能隐藏在“修复”中。

每批完成验证后提交、推送并核对远端 SHA。每次交付建立新的精简阅读包，仅含本轮报告、必要视频、结果与复现入口；完整原始数据单独管理。打包前逐项核对引用文件实际存在，规范见[阅读包说明](../agent_handoff/README.md)。
