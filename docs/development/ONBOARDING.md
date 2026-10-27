# LabSim 组内使用指南

推荐环境是 **`lab_cuvette_loading / Project_release_v1 / standard`**，统一入口为仓库根目录 `./labsim`。按本页完成环境准备、完整任务、标准采集、数据读取和策略接入。项目介绍见[主页](../../README.md)，接口细节见[当前版本技术参考](../lab_cuvette_loading/Project_release_v1/README.md)。

## 准备环境与资产

### 解释器与依赖

使用 Linux、Python 3.11、Isaac Sim 5.1.0 及兼容 NVIDIA GPU/驱动。已有物理验证使用 RTX 4090。同一 GPU 上顺序运行 Isaac 进程。

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
git rev-parse HEAD
git status --short
```

选择已安装 Isaac 的解释器。任务依赖包括 numpy、scipy、omegaconf、h5py、opencv、trimesh、rtree，ACT/DP reader 使用 Torch。`doctor` 检查实际环境及缺失项；依赖变更放在独立工具环境，已有 Isaac 和模型环境保持其锁定版本。

几何审计需要 Shapely>=2.1 的约束三角化接口。已有独立几何环境可直接设置 `LABSIM_GEOMETRY_SITE`。首次建立工具环境：

```bash
"$LABSIM_PYTHON" -m venv "$HOME/.local/share/labsim/geometry"
"$HOME/.local/share/labsim/geometry/bin/python" -m pip install --no-deps "shapely==2.2.0"
export LABSIM_GEOMETRY_SITE="$HOME/.local/share/labsim/geometry/lib/python3.11/site-packages"
```

### 资产获取与检查

```bash
./labsim assets download
./labsim doctor --project-version Project_release_v1 --json
```

[锁文件](../../config/lab_cuvette_loading/Project_v1/assets.lock.json)固定 HF revision、文件大小、SHA256 和来源。匿名下载 82 个 HF 文件及 1 个固定公共来源的 Franka 文件。当前 HF revision 为 `bb880f098180c291f6f65995f969d48047207067`。

默认缓存 `~/.cache/labsim/assets/<revision>/`；`LABSIM_ASSET_CACHE` 设置缓存根目录。完整离线安装保持 `assets/...` 层级：

```bash
./labsim assets install --asset-root /absolute/path/to/new_asset_tree
export LABSIM_ASSET_ROOT=/absolute/path/to/new_asset_tree
./labsim assets check --asset-root "$LABSIM_ASSET_ROOT"
```

`LABSIM_ASSET_ROOT` 优先于默认缓存。离线复用缓存执行 `./labsim assets download --offline`。USD/PhysX 扩展由所选 Isaac distribution 发现。便携资产的路径清理及原/派生 SHA 见[资产语义记录](../lab_cuvette_loading/Project_v1/assets/portable_usd_semantics.json)。

`doctor` 是 CPU 预检。新机器部署还需实际完成下方任务、关闭与读取流程；GUI 另需有效显示环境。

## 运行完整任务

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration \
  --output outputs/lab_cuvette_loading/Project_release_v1/demo_001
```

无显示环境使用 `--headless`。命令执行普通完整 Teacher：来源架抓取 → 离架 → 搬运 → 内座插入 → 支撑交接 → 慢松爪 → 双指脱离 → 撤离 → 至少 3 秒稳定。Teacher 使用物体真值；器皿运动依赖动态刚体接触。

输出目录必须不存在。启动 `LABSIM_STARTUP` 摘要及 `startup_summary.json` 给出实际版本、任务/场景、后端、资产、源/解析配置 SHA、场景指纹、记录模式、用途和目录。运行结束后检查：

- `episode_0000/result.json`：独立任务结果与最终资格。
- `episode_0000/independent_score.json`：评分证据快照；最终资格以事务闭合后的 H5、结果和完成身份为准。
- `episode_0000/dual_view.mp4`、侧视/腕视视频：连续物理过程。
- `episode_0000/dataset/episode_0000.h5` 及完成标记：数据内容和闭合身份。
- `run_manifest.json`：实际版本、运行参数和进程身份。

任务约 126 秒仿真时间；墙钟时间单独记录。可用 `--dry-run` 查看解析命令。`--project-version current` 解析为 `Project_release_v1`，保存真实版本名；省略版本仍兼容历史默认 `Project_v1`。

## 采集标准示范

```bash
export LABSIM_RUN=outputs/lab_cuvette_loading/Project_release_v1/collect_001
./labsim collect --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode collect --record-purpose demonstration --output "$LABSIM_RUN"
```

`--episodes N` 顺序采集完整 Teacher 任务。standard 固定资产、来源槽、邻近器皿、仪器、机器人、相机安装、光照、物理和评分配置。场景随机化关闭，训练 RNG 种子独立管理。

记录模式决定持久化内容：`collect/eval` 保存完整 H5、原生双视角视频与 lossless gzip 物理/接触日志；`diagnostic` 保留详细 plain 日志及额外 collector 视频。用途字段独立声明：示范 `demonstration`、策略评测 `policy_evaluation`、生命周期 `lifecycle_diagnostic`、资源检查 `resource_probe`。

## 读取与移交数据

等待采集进程完全退出，再建立示范用途索引并读成功 batch：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$LABSIM_RUN" \
  --purpose demonstration --output "$LABSIM_RUN/index/demonstrations.hdf5"
./labsim dataset-check --index "$LABSIM_RUN/index/demonstrations.hdf5" \
  --sample-filter success --policy both --output "$LABSIM_RUN/read_success.json"
```

`--purpose` 决定集合，`--sample-filter success|failure|all_valid` 决定资格。BC 使用合格示范成功；有效失败按明确用途分析。索引回执列出纳入、排除、原因、源 H5 哈希和各资格数量。历史用途通过身份/文件哈希绑定 sidecar 补充，原 H5 和标签保留。

ACT/DP 数据为两路 CHW uint8 RGB；正常数据读取器生成实际 batch。训练动作 8 维：7 个臂关节绝对位置目标（rad）及 1 个单指位置（m）。实际 9 维双指命令、请求动作、后继状态和逐步每指驱动上限另存。按完整 episode 划分 train/validation，两者保持 standard。

相对外链默认 `relative-links`：移交索引及全部来源 H5，保留相对目录。检查依赖：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.transfer \
  "$LABSIM_RUN/index/demonstrations.hdf5" --verify-sha256 \
  --output "$LABSIM_RUN/dependencies.json"
```

需要独立移动的自包含 HDF5 时，索引构建加 `--mode copy`。RGB 兼容别名保留 hardlink。完整教程、缺失文件处理、同机活动 writer 保护及历史诊断读取见[数据用途与移交](../lab_cuvette_loading/Project_release_v1/data_usage.md)。

[公开缩图样例](../../config/lab_cuvette_loading/Project_v1/public_samples.json)属于早期 `Project_v1`，图像 96 像素，保留完整时间序列；其版本及图像派生声明随样例保留。

## 接入策略与开展评测

Teacher 评测示例：

```bash
./labsim eval --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/eval_001
```

外部策略先启动环境服务：

```bash
./labsim serve --project-version Project_release_v1 --headless --port 8097 \
  --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/rpc_001
```

在另一终端运行客户端，顺序调用 `reset / observe / execute / receipt / status / finish / close`。最小客户端、π0.5 与 Harness 的部署、输入/输出适配见[可选策略](../../policy/backends/OPTIONAL_POLICIES.md)及[当前外部策略契约](../lab_cuvette_loading/Project_release_v1/external_policy/contract.md)。GPT 使用 `eval --project-version Project_release_v1 --backend gpt6`，显式配置独立凭据和预算后调用；凭据放在仓库及输出之外。

模型等待时物理暂停，执行有界动作时按控制/物理步推进。外部策略不接收器皿位姿、插入深度或评分内部真值。Teacher、GPT、π0.5、Harness 和自有策略的能力范围见[主页策略表](../../README.md#策略接入与评测)。

### 策略接口与时序

公开观察包含 episode/observation ID、仿真时间、双 RGB、相机标定、关节位置/速度、TCP 位姿、夹爪开口/力限制、任务文本和声明的器皿过滤指端法向接触模长。

| 动作 | 数值与单位 | 坐标与主要限制 |
|---|---|---|
| `ee_delta` | xyz 位移 m + 旋转向量 rad，共 6 维 | world/TCP；每动作位移范数≤0.04 m、转角≤0.15 rad |
| `ee_pose` | xyz m + 单位 wxyz 四元数，共 7 维 | world 绝对目标；相同执行限制 |
| `joint_position` | 7 臂关节 rad，或含双指的 9 维 | 实际机器人关节范围；双指对称 |
| `joint_velocity` | 7 臂关节 rad/s | 速度/关节/轨迹安全限制 |
| 夹爪字段 | 双指总开口 m；每指驱动力上限 N | 总开口 0–0.08 m；每指上限 0–8 N |

动作必须携带 `action_id / episode_id / observation_id / type / values / duration_s`。持续时间为 60 Hz 控制周期的整倍数，单次≤3秒；末端平移速度≤0.02 m/s、角速度≤0.15 rad/s，连续 IK 还检查关节和路径。原始请求、实际执行动作与后继状态分别保存。

`accepted` 表示预检通过；`execution_finished` 表示执行区间闭合；`target_reached` 是实际 TCP 端点 1 mm / 0.5° 规格及完整执行检查。安全停止和部分执行保留真实步数与回执。旧 observation 拒绝；相同 action ID 返回既有回执，避免网络重试重复运动。`finish` 请求独立判分。

`GenericContactHold` 保持手指命令，靠物理接触抓持；每指驱动上限与实测接触力分别记录。精细位移诊断的测量对象为**空夹爪仿真 TCP**，规格和实际测量见历史技术记录。

### 图像与任务文本

三层处理分别定义：环境/公开相机原生 HWC RGB uint8；H5/训练 reader 的缩放及 CHW 数据；checkpoint 的实际 processor。π0.5 客户端保留原生 640×480，服务收到 `[1,480,640,3]`，checkpoint 再缩放/填边和归一化。完整 shape、转换位置、实际 tokenizer 及任务文本截断审计见[外部策略契约](../lab_cuvette_loading/Project_release_v1/external_policy/contract.md)。

当前部署任务文本 264 tokens，上限 200，尾部被截断。使用契约中的本地审计入口核对有效输入；修改提示词时使用独立配置与指纹。

## 安装检查与生命周期验收

需要先做最短 GUI 安装检查时：

```bash
./labsim demo --project-version Project_release_v1 --sequence early_finish --gui \
  --record-mode diagnostic --record-purpose lifecycle_diagnostic \
  --output outputs/lab_cuvette_loading/Project_release_v1/install_check_001
```

它真实推进三秒并提前结束。生命周期开发验证使用显式混合序列：

```bash
./labsim collect --project-version Project_release_v1 --headless \
  --sequence teacher early_finish teacher --record-mode collect \
  --record-purpose lifecycle_diagnostic \
  --output outputs/lab_cuvette_loading/Project_release_v1/lifecycle_001
```

诊断索引显式选择 `--purpose lifecycle_diagnostic`。历史三集通过 sidecar 声明用途，资格读取仍为 success/failure/all_valid = 2/1/3，见[数据验收](../lab_cuvette_loading/Internal_use_v1/20261028/data_usage/README.md)。生命周期机制及原始历史验收说明见[lifecycle.md](../lab_cuvette_loading/Project_release_v1/lifecycle.md)。

## 常见问题与处理

| 现象 | 处理 |
|---|---|
| 找不到 Isaac/USD 或几何接口 | 检查 `LABSIM_PYTHON`、独立 `LABSIM_GEOMETRY_SITE`，运行显式版本 doctor |
| 资产缺失/哈希不符 | 使用锁定 revision 下载或完整已校验资产根目录 |
| 输出目录已存在 | 选择新目录，保留原失败与中断结果 |
| 正式索引为空 | 检查用途、完成状态及 `.index.json` 排除原因；历史用途用 sidecar |
| 索引移动后缺 H5 | 运行 transfer，按列出的相对路径携带来源文件，或用 copy |
| 任务失败、程序退出正常 | 读取独立结果、终止原因、记录资格；任务成败与服务状态分开 |
| π0.5 任务文本截断 | 本地 tokenizer 审计有效输入；新文本使用独立配置 |
| 退出出现 `ManipulatorFactory` SDK 回调错误 | 核对数据完成标记、文件闭合与进程退出凭据；保留日志，使用已记录 SDK 版本 |
| 长批次 RSS 增长 | 分组采集、正常关闭进程并监测资源；长程内存定位单独管理 |
| PID 检查提示 writer 活动 | 同机确认原采集进程已关闭；跨机/PID 复用按数据指南保留关闭凭据交维护者处理 |

## 实现地图与开发验证

| 入口/模块 | 职责 |
|---|---|
| `labsim` → `scripts/labsim_cli.py` | 版本解析、路由、参数和防覆盖 |
| `demos/lab_cuvette_project_release_v1/launch.py` | 普通完整 Teacher/GPT/RPC，创建 SimulationApp 与顺序采集 |
| `demos/lab_cuvette_project_release_v1/run.py` | 显式生命周期验收序列 |
| `tasks/lab_cuvette_loading_project_release.py` | 任务注册、事务闭合和完成资格 |
| `demos/lab_cuvette_project_release_v1/environment.py` | 发布版生命周期 facade，继承已验证执行器 |
| `controllers/lab_cuvette_env_v1_controller.py` | Teacher 接触锁存、搬运、支撑交接及卸载 |
| `data_collectors/lab_cuvette_project_release_collector.py` | 流式 H5、完整性、完成身份和索引发布 |
| `demos/lab_cuvette_project_release_v1/{dataset_index,membership,transfer}.py` | 用途集合、历史 sidecar、数据移交 |
| `policy/dataset/lab_cuvette_project_release_dataset.py` | 正式 ACT/DP release 资格 reader |
| `policy_backends/lab_cuvette_env_v1/` | 外部模型服务、适配及输入审计 |

当前配置：[standard.yaml](../../config/lab_cuvette_loading/Project_release_v1/standard.yaml)。发布版固定 `cuvette_xy_1000`；其它已注册尺寸通过[历史尺寸研究入口](../lab_cuvette_loading/Size_v1/README.md)管理。

CPU 验证见[工作流](../../.github/workflows/cpu-contracts.yml)与独立 [CI 依赖](../../requirements/ci.txt)。真实 Isaac 运行另外记录运行提交、配置/资产指纹、退出凭据、独立结果和实际 reader。历史物理/标签保持原样。

日常工作沿用 `codex/labsim`，遵循[贡献规范](../../CONTRIBUTING.md)。每批验证后提交并推送；每次交付生成只含本次改动与结果的[精简阅读包](../agent_handoff/README.md)。
