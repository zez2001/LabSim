# Project_v1_1 调用说明

本文说明独立版本的调用入口。物理运行结果以本版本的实际输出和独立评分为准；命令存在和 CPU 测试通过本身不代表完整任务成功。

## 版本与环境

`./labsim` 保留既有默认行为：省略版本时仍运行 `Project_v1`。调用本版本必须显式增加 `--project-version Project_v1_1`。四个执行入口 `demo`、`eval`、`collect`、`serve` 使用相同的版本选择规则，路由至 `demos.lab_cuvette_project_v1_1.run` 和 `config/lab_cuvette_loading/Project_v1_1/standard.yaml`。

继续使用现有 Isaac Sim 5.1 / Python 3.11 环境，不在其中安装 CI 依赖。若包装器未找到正确解释器，可显式指定：

```bash
export LABSIM_PYTHON=/path/to/existing/python3.11
./labsim doctor --json
./labsim assets check
```

`doctor` 当前检查共享运行环境和原 Project_v1 资产基础，并未替代新版本的物理验收。资产取得和部署说明沿用项目主页。所有输出必须使用不存在的新路径；同一张 GPU 上顺序运行仿真。

## 演示、评测与采集

先查看真实启动参数。`--dry-run` 不创建输出目录，不启动仿真，也不调用模型：

```bash
./labsim demo --project-version Project_v1_1 \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_preview_01 --dry-run
```

运行一次 GUI 专家演示：

```bash
./labsim demo --project-version Project_v1_1 --backend teacher \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_demo_01
```

标准场景内顺序评测五集：

```bash
./labsim eval --project-version Project_v1_1 --backend teacher --episodes 5 --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_eval5_01
```

采集入口使用同一环境、观测—动作时间对齐和独立判分。场景保持 `standard`，不增加布局随机化：

```bash
./labsim collect --project-version Project_v1_1 --episodes 1 --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/collect_standard_01
```

历史 `collect --phase ... --collection ...` 专属于 Size_v1，不能与本版本混用。新旧数据和输出不互相覆盖。

直接 GPT 控制选择 `--backend gpt6`。仅在本地凭据环境已就绪且预算已设置后运行；不把密钥放进配置、命令参数或输出：

```bash
./labsim demo --project-version Project_v1_1 --backend gpt6 --max-calls 160 --headless \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_demo_01
```

上述 ledger 与前轮共用，保留既有请求和费用占用；不要用空 ledger 重置预算。

独立的 `policies/cubence_gpt6_context4.json` 只减少历史记忆至两个完整工具回合。每步当前公开观测、任务说明、双图与标定仍然发送。使用上方命令增加以下参数即可选择；不能把 CPU 结构验证当作该配置下的完整任务成功：

```bash
--provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4.json
```

公开 loading 目标从配置说明名义 27 mm 深度、67.5 mm 器皿高度及 40.5 mm 露出长度，不提供当前器皿位姿或深度。接触保持 v2 使用已声明的手指传感器与 effort 上限，小幅补足既有质量/摩擦假设下的预载；它不改变物理参数或评分，也不保证任务成功。低 effort 和显式慢张爪优先，实际目标、实测力及附加闭合边界均进入逐控制周期记录。

模型控制器通过公开观测和受约束动作接口执行。专家控制器与 GPT 控制器的能力和输入范围分别以运行时元数据记录，不能混用其结果统计。

## 已有 policy 的 RPC 入口

```bash
./labsim serve --project-version Project_v1_1 --headless --port 8097 \
  --output outputs/lab_cuvette_loading/Project_v1_1/policy_rpc_01
```

服务器保留已有 loopback RPC 协议。π0.5 / Harness 等客户端的独立部署步骤见 `policy/backends/OPTIONAL_POLICIES.md`；该文档中省略版本的示例仍调用原 Project_v1，测试本版本时应替换为上方启动命令。没有策略请求时仿真暂停，不启动第二个 Isaac 进程。

## 正常读取 ACT / Diffusion Policy batch

只读取已经关闭的 episode 或完整 episode 索引。此入口根据 H5 的 `scene_version` 自动选择 reader；不需要额外指定版本，也不会修改原始 H5：

```bash
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_v1_1/teacher_demo_01/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_demo_01_read_check.json
```

有效任务失败改用 `--sample-filter failure`。正常成功训练入口要求完整装载、记录完整性通过、物理结果可信及 `success_bc_eligible=true`。执行器、服务或仿真异常保留诊断资格，不能通过修改标签进入成功训练集。不同场景版本或冻结指纹不得混入同一索引。

Python 调用复用同一 reader：

```python
from scripts.read_lab_cuvette_project_v1_data import read_check
from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset

result = read_check(
    "path/to/closed/episode_0000.h5",
    sample_filter="success",
    policies=("act", "dp"),
    dataset_class=LabCuvetteProjectV11Dataset,
)
```

省略 `dataset_class` 仍使用旧 Project_v1 reader，不会自动改写旧调用语义。公开 HF 的既有 Project_v1 示例保留原版本标签，不应当成 Project_v1_1 的运行证据。

## CPU 接口检查

CI 的轻量契约任务覆盖新配置、执行器、独立判分、环境与工具行为；单独的 CPU reader 任务安装 CPU Torch、h5py、OpenCV 与 zarr，实际生成小 H5 fixture 并读取 ACT / DP batch。fixture 仅验证数据接口，不是仿真成功证据。不要将 `requirements/ci*.txt` 安装进既有 Isaac 环境。

主要相关文件：

- 入口：`scripts/labsim_cli.py`。
- 本版本配置：`config/lab_cuvette_loading/Project_v1_1/standard.yaml`。
- 环境和执行入口：`demos/lab_cuvette_project_v1_1/`。
- 采集：`data_collectors/lab_cuvette_project_v1_1_collector.py`。
- 正常读取器：`policy/dataset/lab_cuvette_project_v1_1_dataset.py`。
- 读取验证：`scripts/read_lab_cuvette_project_v1_data.py`。

资产、物理参数和判分门槛是否发生变化，应以版本配置及提交差异核对；本调用入口本身不修改这些内容。

## 确定性执行诊断

以下入口不调用模型。`free-space-checked` 将两种固定完整位姿和 world/TCP 的 72 个有符号位移分为三个独立 reset 的 episode，避免旧诊断的累计时长和朝向漂移。`fine-preinsert` 在合法空爪预插入位置测量 0.1、0.5、1、2 mm；`grasp-transport` 是公开通用工具的人工动作诊断，不是 GPT 完整任务成功。

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_v1_1.run \
  --backend diagnostic --probe free-space-checked --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/free_checked_new
```

新配置显式启用仅用机器人状态的有界跟踪补偿，并使用腕相机 v2 固定挂点。实际效果与未完成项目见本版本诊断和最终结果记录。teacher 每次阶段变化保存无 GT 裁剪的原生帧和两种编码预览，均标明未发送 API；GPT 的真正发送输入位于 `gpt_control/observations`。

配置版本字段分别为 `project.camera_version`、`project.executor_version`、`robot_tracking.version`。新 teacher 的 `teacher_execution.motion_time_scale` 只放慢快速移动阶段；插入、支撑交接、开爪、稳定观察和安全计时仍使用真实仿真时间。原保护阈值、物理参数和历史 teacher 保持原样。
