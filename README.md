# LabSim

基于 LabUtopia 和 Isaac Sim 的科学实验操作仿真工程。当前正式任务是 **`lab_cuvette_loading / Size_v1`**：Franka 从白色 6×6 来源架抓取比色皿，搬运到开盖仪器的内部座，完成插入、支撑交接、松爪、撤离与 3 秒稳定观察，并记录可供 ACT / Diffusion 读取的轨迹。

**开发与交接入口：[`codex/labsim`](https://github.com/zez2001/LabSim/tree/codex/labsim)。** `main` 保留 LabUtopia 上游基准。日常修复和同一功能的改进继续使用当前分支；独立功能才另开短期分支。具体约定见 [贡献与分支规则](CONTRIBUTING.md)。

## 功能与验证范围

- 独立场景：单台开盖仪器、原始内部 A 座、完整参数化 6×6 架、动态空心比色皿、Franka、侧视与腕部相机。
- 完整物理执行：来源架取物 → 拔出 → 搬运 → 对准 → 插入 → 承托交接 → 对称慢松爪 → 撤离 → 稳定。专家控制器使用器皿真值位姿和接触反馈。
- 连续双指接触锁存、按阶段卸载、卡滞检测与独立判分；锁存的是夹指位置命令，不是把物体绑定到机器人。
- 采集双相机 RGB、机器人状态、原始及实际动作、时间戳、物体位姿、接触与任务阶段；保留成功、失败和未执行状态。
- 35 个独立尺寸资产及注册表，通过 `asset_id` 选择；支持几何筛选、冻结场景校验、数据审计和正常 ACT / Diffusion 数据读取。
- 保留早期 `minimal_pick`、精密插入及器皿装载各版本，入口见[历史实验索引](docs/history/README.md)。

当前正式配置使用 **10.0×10.0×67.5 mm** 比色皿、20 g 质量假设、来源槽 A1、原内部 A 座 `candidate_far_hinge`。原座几何、尺寸、碰撞和物理参数保持不变。尺寸资产属于工程假设，不是实物测量结果。

已实际完成固定场景 **5/5** 验证，并采集 **20 条合格完整成功 + 20 条有效失败**。失败均为确定性动作偏差：在 1 / 5 / 10 / 18 mm 插入深度提前停止，各 5 条；没有自然失败，不能据此解释为自然卡滞。全部 40 条通过实际事件、进程、冻结与读取审计。成功和失败分别按完整 episode 划分 18 train / 2 val；本轮未执行训练。

[结果报告与连续录像](docs/lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.md) · [DOCX](docs/lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.docx) · [40 条数据审计](docs/lab_cuvette_loading/Size_v1/data/final40_actual/README.md)

## 环境与获取

已运行环境为 Linux、NVIDIA RTX 4090、Python 3.11、Isaac Sim 5.1；物理 240 Hz、控制 60 Hz。GPU 仿真顺序运行。代码、配置和资产在 Git / Git LFS 中；约 61 GB 原始数据及 Python 环境不随普通 clone 提供。

```bash
git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
git lfs install
git lfs pull
```

**当前电脑**可复用项目同级的 `../labutopia-env/bin/python`。其他位置显式设置解释器，再运行只读检查：

```bash
export LABSIM_PYTHON=/absolute/path/to/python
./labsim doctor
./labsim --help
```

`doctor` 检查解释器、依赖发现、LFS 实体、冻结文件和路径，并报告可迁移性问题；它不启动 Isaac Sim，也不等同于 GPU / GUI 运行通过。新机器请先阅读[开发接入指南](docs/development/ONBOARDING.md)：当前仍有既有环境路径依赖，不能只安装 Python 包就认定部署完成。上游安装参考已移至 [LabUtopia 文档](docs/upstream/README.labutopia.md)。

## 运行完整 GUI demo

以下命令均在仓库根目录执行。`outputs/` 下的名称是示例新输出位置，请为每次运行使用尚不存在的目录。默认 GUI；无桌面显示时增加 `--headless`。

```bash
./labsim demo --output outputs/lab_cuvette_loading/Size_v1/demo_handoff_001 --dry-run
./labsim demo --output outputs/lab_cuvette_loading/Size_v1/demo_handoff_001
```

默认任务固定为正式 Size_v1 standard 场景。单次成功轨迹约 106 秒仿真时间，实际墙钟时间受硬件和图像记录影响。输出保留连续录像、episode、事件与独立结果；依据实际结果判断成功，不能以进程正常结束代替任务成功。

## 固定场景采集

先在全新 collection 完成 5 次验证；通过后，沿用同一个 collection 补采成功和确定性动作偏差失败：

```bash
./labsim collect --phase verify5 --collection outputs/lab_cuvette_loading/Size_v1/collection_handoff_001 --headless
./labsim collect --phase success --collection outputs/lab_cuvette_loading/Size_v1/collection_handoff_001 \
  --allow-after-verified-five --headless
./labsim collect --phase controlled_failure --collection outputs/lab_cuvette_loading/Size_v1/collection_handoff_001 \
  --allow-after-verified-five --headless
```

只需检查命令和路径时追加 `--dry-run`。采集会检查冻结依赖并保持 standard；布局、资产、光照和物理随机化均关闭。训练随机种子与场景随机化是不同设置。失败组保持 `task_success=false`，不会混入成功 BC 数据。阶段驱动退出码 2 可表示配额尚未满足，须结合保存的仿真子进程退出码与逐集结果解释。

## 审计与读取数据

等待该 collection 的所有仿真进程退出后再审计。新索引和审计文件不能已经存在：

```bash
./labsim validate --collection outputs/lab_cuvette_loading/Size_v1/collection_handoff_001 \
  --index outputs/lab_cuvette_loading/Size_v1/collection_handoff_001/dataset/episode_data.hdf5 \
  --output outputs/lab_cuvette_loading/Size_v1/collection_handoff_001/audit/collection.json

./labsim dataset-check \
  --index outputs/lab_cuvette_loading/Size_v1/collection_handoff_001/dataset/episode_data.hdf5 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Size_v1/collection_handoff_001/audit/success_read.json
```

失败读取把 `--sample-filter` 改为 `failure`，同时改用新的输出 JSON。`dataset-check` 通过正常 ACT / DP 读取器检查 batch，不启动训练。正式索引文件名为 `episode_data.hdf5`；轻索引使用 collection 内相对链接，移动时需保留完整 collection 树。单集可独立导出，已有便携样例证据见[数据接入说明](docs/lab_cuvette_loading/Size_v1/data/standard5_actual/README.md)。

Git 中提供审计结果和少量代表媒体。已有完整数据在本机 `outputs/lab_cuvette_loading/Size_v1/collection_standard/`，交接时需单独传输或重新采集；只有 clone 代码不会得到这些 episode。

## 资产与扩展

```bash
./labsim assets
./labsim assets --asset-id cuvette_xy_1000 --json
```

资产注册表在 [registry.json](assets/lab_cuvette_loading/Size_v1/registry.json)。正式场景冻结为 10 mm；测试其他尺寸使用独立未冻结配置，不能覆盖正式资产或自动继承其成功资格。35 个候选均保留同一 XY 仿射派生规则、高度、空腔和底部拓扑，视觉与碰撞同步变换；固定 20 g 时重新积分质心和惯量，不同时假设密度保持不变。

新增尺寸、几何扫描和高级底层命令见 [Size_v1 使用说明](demos/lab_cuvette_size_v1/README.md)。现有环境接口、动作语义和实现位置见[开发接入指南](docs/development/ONBOARDING.md)。ACT / DP 训练配置已接入，但本轮仅验证配置合成及数据读取；后续训练须显式启动，默认只读合格成功、保持 standard。

## 目录导航

```text
labsim                      稳定命令入口；scripts/labsim_cli.py 分派
assets/lab_cuvette_loading/  原始来源、历史派生资产及 Size_v1 注册表
config/lab_cuvette_loading/  各版本场景、冻结配置和物理参数
demos/lab_cuvette_size_v1/   正式任务组合与尺寸实验
tasks/                      环境 API、场景和观测实现
controllers/                机器人控制与任务执行
data_collectors/            既有记录管线
policy/                     ACT / DP 数据集与训练配置
scripts/                    采集、审计、读取、打包和维护工具
tests/                      CPU 回归及明确标注的仿真检查
docs/development/           接入与开发说明
docs/history/               历史实验入口和归档
outputs/                    本地产生的大数据；不默认加入 Git
```

## 已知边界

- 10.0 和 10.3 mm 有实际完整成功记录；10.5 mm 开发运行质量判分失败。几何正证书最大已观察到 10.70 mm，不能据此给出连续物理可用上限。
- 来源架尺寸、20 g 质量及接触材料仍含工程假设；未做真实设备校准。原 12.5 mm 器皿与原座的配套结论没有改写为成功。
- 保留原生速度与位姿差分不一致告警；静态原座完整 PhysX 烹饪表示尚不能完整读回。几何抽样误差不是严格全局误差界。
- 专家使用仿真真值；完整示范成功不等于视觉策略已训练或闭环评测通过，不包含液体、光谱、玻璃破碎或真机操作。
- 新机器完整部署尚需独立验证。冻结依赖改变后应建立新实验版本，不能把旧场景指纹直接赋给修改后的任务。

## 开发交接与来源

新开发者先运行 `doctor`，核对[开发接入指南](docs/development/ONBOARDING.md)，再用全新目录运行一次完整 demo。修改前明确资产、控制、评分和数据影响，按[贡献规则](CONTRIBUTING.md)提交、验证与推送。历史过程保留在[历史索引](docs/history/README.md)，主页只维护当前支持功能、使用方法和边界。

GitHub [CPU contracts](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml) 检查 CLI、控制状态机、评分和数据语义，不启动 Isaac 或训练。其轻量依赖独立列在 [requirements/ci.txt](requirements/ci.txt)，应装入新的 CPU 检查环境，不要改动已有仿真环境。具体测试命令见工作流及[本次验证记录](docs/development/validation/verification_summary.json)。开发分支禁止强推和删除，短期功能分支合入后自动清理；日常迭代不要求新建分支。

LabSim 基于 [LabUtopia](https://github.com/Rui-li023/LabUtopia)。上游原文、论文引用及资产授权说明见[上游文档](docs/upstream/README.labutopia.md)；代码许可证见 [LICENSE](LICENSE)。外部 CAD 与其他第三方资产的来源和适用范围以各版本清单为准，仓库代码许可证不自动替代第三方资产授权。项目背景见[背景文档](docs/background/README.md)。
