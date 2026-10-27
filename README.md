# LabSim

LabSim 是面向科学实验机器人的 Isaac Sim 仿真项目，提供完整物理任务、标准示范采集和统一策略评测接口。当前任务 `lab_cuvette_loading`：Franka 从白色 6×6 来源架抓取比色皿，离架搬运至开盖仪器的内部 A 座，完成插入、支撑交接、松爪、脱指、撤离与至少 3 秒稳定观察。

当前推荐版本为 **`Project_release_v1`**，长期开发分支为 **`codex/labsim`**。

[English](README_EN.md) · [中文导航](README_CN.md) · [组内使用指南](docs/development/ONBOARDING.md) · [版本与技术参考](docs/lab_cuvette_loading/Project_release_v1/README.md) · [公开资产](https://huggingface.co/datasets/Txie000/SLAI-Labsim)

## 完整演示

[![Franka 连续器皿装载](docs/lab_cuvette_loading/Internal_use_v1/20261028/media/scene.png)](docs/lab_cuvette_loading/Internal_use_v1/20261028/media/teacher_full.mp4)

[观看连续 Teacher 完整任务](docs/lab_cuvette_loading/Internal_use_v1/20261028/media/teacher_full.mp4)。Teacher 使用任务真值完成物理抓取与装载，视频覆盖来源架初态至撤离后稳定。各策略的使用范围见下方策略表。

## 当前能力

| 模块 | 功能 | 典型用途 |
|---|---|---|
| 数字资产与标准场景 | Franka、完整 6×6 来源架、单台开盖仪器、内部 A 座、尺寸变体注册与来源追溯 | 固定场景操作实验、资产尺寸研究 |
| 完整物理任务 | 抓取、离架、搬运、插入、承托交接、慢松爪、脱指、撤离与稳定判定 | 端到端示范、任务阶段分析 |
| 精细执行 | 末端/关节动作、连续 IK、实际状态跟踪、有界执行、幂等回执与误差诊断 | 策略动作接入、空夹爪仿真 TCP 跟踪测量 |
| 数据采集 | 双视角 RGB、机器人状态、请求/执行动作、后继状态、接触、事件与时间戳 | ACT/DP 数据读取、失败分析 |
| 独立评测 | 阶段进度、完整成功、终止原因、记录完整性、物理质量与数据资格 | 策略比较、合格示范筛选 |
| 项目接口 | 统一 CLI、Teacher、GPT 直接控制、π0.5 RPC、Harness、自有策略生命周期 | 组内复用、外部策略评测 |

发布版固定 standard 场景：`cuvette_xy_1000`（10×10×67.5 mm 尺寸假设、20 g 工程质量假设）、来源槽 A1、远角蓝色器皿 F6、原内部 A 座 `candidate_far_hinge`；物理 240 Hz、控制 60 Hz。采集与训练数据准备关闭场景随机化。资产依据、尺寸系列和真实测量待补项集中见[资产说明](docs/lab_cuvette_loading/Project_release_v1/README.md#资产与物理规格)。

## 安装与资产获取

已使用的运行环境：Linux、Python 3.11、Isaac Sim 5.1.0、NVIDIA RTX 4090。先准备已有 Isaac 解释器及独立几何工具环境，步骤见[准备环境与资产](docs/development/ONBOARDING.md#准备环境与资产)。同一 GPU 顺序运行 Isaac 进程。

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
./labsim assets download
./labsim doctor --project-version Project_release_v1 --json
```

资产匿名下载并按[锁文件](config/lab_cuvette_loading/Project_v1/assets.lock.json)校验，固定 HF revision [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)。83 个依赖文件中 82 个来自 HF，Franka 来自锁定的公共来源。默认缓存 `~/.cache/labsim/assets/<revision>/`；可设置 `LABSIM_ASSET_CACHE` 或完整的 `LABSIM_ASSET_ROOT`。

## 完整任务快速开始

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration \
  --output outputs/lab_cuvette_loading/Project_release_v1/demo_001
```

这是普通完整任务入口。无桌面时把 `--gui` 换成 `--headless`；输出目录须为新路径。启动摘要显示实际版本、任务、场景、策略、资产、配置/场景指纹、记录模式、用途及输出目录。完成后查看 `episode_0000/result.json`、独立评分、`dual_view.mp4` 和最终完成资格。完整任务约 126 秒仿真时间，墙钟耗时受图像采集影响。

`--project-version current` 是当前版本快捷别名，记录中保存解析后的 `Project_release_v1`。省略版本保留兼容默认 `Project_v1`。三秒安装检查及混合生命周期序列另见[开发验收](docs/development/ONBOARDING.md#安装检查与生命周期验收)。

## 标准采集与数据读取

```bash
export LABSIM_RUN=outputs/lab_cuvette_loading/Project_release_v1/collect_001
./labsim collect --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode collect --record-purpose demonstration --output "$LABSIM_RUN"

# 等待采集进程退出后执行。
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_release_v1.dataset_index "$LABSIM_RUN" \
  --purpose demonstration --output "$LABSIM_RUN/index/demonstrations.hdf5"
./labsim dataset-check --index "$LABSIM_RUN/index/demonstrations.hdf5" \
  --sample-filter success --policy both --output "$LABSIM_RUN/read_success.json"
```

用途选择与任务资格分开：`demonstration` 选择示范集合，`success` 再筛选合格完整成功。ACT/DP 正常 reader 读取实际 batch；动作是 7 个臂关节绝对位置目标加 1 个单指位置，共 8 维，9 维双指实际命令另存。训练/验证按完整 episode 划分。

索引默认 `relative-links`，须连同来源 H5 保持相对目录移交；`--mode copy` 生成自包含文件并保留图像 hardlink 别名。用途、历史 sidecar、资格规则和移交依赖检查见[数据使用与移交](docs/lab_cuvette_loading/Project_release_v1/data_usage.md)。`collect/eval` 均保存完整 H5、原生视频及压缩物理日志，`diagnostic` 另保留详细日志；记录模式与用途分别配置。

## 策略接入与评测

| 策略 | 提供的功能 | 典型入口 |
|---|---|---|
| Teacher | 完整物理装载示范 | `demo` / `collect --backend teacher` |
| GPT 直接控制 | 图像闭环抓取、离架与搬运 | `eval --backend gpt6`，独立凭据与预算 |
| π0.5 | 真实模型连续 RPC 交互、动作回执、安全终止与数据回读 | 环境 `serve` + 模型服务 + 适配客户端 |
| Harness | 本地 RPC 接入及已有短程调用 | `serve` + Harness 客户端 |
| ACT / DP | 正常数据 reader 与实际 batch 读取 | `dataset-check --policy both` |
| 自有策略 | 统一观察、动作执行和生命周期 | `reset / observe / execute / receipt / status / finish / close` |

```bash
# Teacher 评测；评测用途与示范用途分别建索引。
./labsim eval --project-version Project_release_v1 --backend teacher --headless \
  --episodes 1 --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/eval_001

# 启动环境服务，随后在另一终端连接策略客户端。
./labsim serve --project-version Project_release_v1 --headless --port 8097 \
  --record-mode eval --record-purpose policy_evaluation \
  --output outputs/lab_cuvette_loading/Project_release_v1/rpc_001
```

公开观测提供双相机、机器人状态及声明的接触信号。模型等待时仿真暂停，动作执行按规定物理步推进。末端动作使用米/弧度、world/TCP 坐标系与 wxyz 四元数；具体输入、限幅、回执及图像三层契约见[使用指南](docs/development/ONBOARDING.md#策略接口与时序)和[外部策略契约](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md)。当前 π0.5 部署的任务文本存在 264→200 token 截断，部署审计和处理入口集中在[输入审计](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md)。

## 文档导航、来源与许可

- [组内使用指南](docs/development/ONBOARDING.md)：准备环境 → 完整任务 → 采集 → 读取 → 策略接入；常见问题及实现地图。
- [当前版本技术参考](docs/lab_cuvette_loading/Project_release_v1/README.md)：资产规格、接口和验收证据导航。
- [数据用途与移交](docs/lab_cuvette_loading/Project_release_v1/data_usage.md) · [可选策略部署](policy/backends/OPTIONAL_POLICIES.md)。
- [历史版本](docs/history/README.md) · [贡献规范](CONTRIBUTING.md) · [CPU CI](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml) · [结果阅读包](docs/agent_handoff/README.md)。

项目基于 [LabUtopia](https://github.com/Rui-li023/LabUtopia)，引用见[上游文档](docs/upstream/README.labutopia.md)，代码许可见 [LICENSE](LICENSE)。第三方资产按[锁文件来源与授权](config/lab_cuvette_loading/Project_v1/assets.lock.json)使用；外部仪器与比色皿 CAD 及派生模型获项目所有者公开再分发授权。当前为刚体纯仿真任务；实物质量、摩擦与动力学采用明确工程假设，真实校准另行进行。
