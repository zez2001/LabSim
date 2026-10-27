# LabSim Project_v1_1

`lab_cuvette_loading` 的独立执行版本：Franka 从白色 6×6 来源架取出比色皿，搬运至单台开盖仪器的内部 A 座，插入、交接支撑、松爪、撤离，再观察至少 3 秒。提供确定性 teacher、GPT 图像控制、本地 policy RPC、连续录像、H5 采集和独立判分。

本版本复用原资产与物理基线，增加连续 IK、动作执行回执、机器人状态跟踪补偿与接触保持。teacher 可以使用器皿真值；GPT 只接收公开 RGB、机器人状态、相机标定与指端接触。二者的控制能力和成绩分别记录。公开 `finger_contact_N` 是按器皿过滤的左右指法向接触向量模长，不能解释为全物体触觉、摩擦力或目标底部支撑力。场景包含工程假设，`real_calibrated=false`；尺寸适配任务成功不等于原型号配套或真实仪器校准。

[项目首页](../../../README.md) · [完整 teacher 录像](media/teacher_support_align_01_full.mp4) · [首条成功与便携读取证据](diagnostics/teacher_support_align_01_support_portability_audit/README.md) · [公开图像历史输入与 P6](public_temporal_visual_context_v1.md) · [固定侧视细节候选 P7](fixed_side_detail_P7.md)

## 运行准备

需要 Linux、Python 3.11、Isaac Sim 5.1 和 NVIDIA GPU。使用已有 Isaac Python 环境，不向其中安装 CI 或模型依赖。同一 GPU 顺序运行仿真。

```bash
# 在 LabSim checkout 中，选择已安装 Isaac 的解释器
export LABSIM_PYTHON=/absolute/path/to/existing/isaac-python

# 资产缓存与 checkout 独立；多个 checkout 可复用同一已验证缓存
export LABSIM_ASSET_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/labsim/assets"
./labsim assets download
./labsim assets check --asset-root \
  "$LABSIM_ASSET_CACHE/bb880f098180c291f6f65995f969d48047207067"
./labsim doctor --json
```

几何工具沿用项目首页的独立 Shapely 环境；需要自定义位置时设置 `LABSIM_GEOMETRY_SITE` 为其 Python 3.11 site-packages。不要复制开发机器上的 `/tmp/...clean...`、挂载盘或作者环境绝对路径。CLI 自动使用当前 checkout、所选解释器和安装好的 Isaac 扩展；生成的几何审计缓存属于当前 checkout 的输出目录。

固定资产 revision 仍为 [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)，共 83 个声明文件：82 个 HF 文件和一个固定公共 Git LFS 来源的 Franka 文件。按[锁文件](../../../config/lab_cuvette_loading/Project_v1/assets.lock.json)校验大小与 SHA256；HF 下载无需登录。Franka 未重新上传 HF，其再分发许可证仍未核实；资产不统一套用代码 MIT 许可。

默认下载完成后，运行入口自动选择该 revision 缓存。另一种部署方式是安装完整 `assets/...` 树，运行时显式指定它：

```bash
export LABSIM_ASSET_ROOT=/absolute/path/to/labsim-asset-install
./labsim assets install --asset-root "$LABSIM_ASSET_ROOT"
./labsim assets check --asset-root "$LABSIM_ASSET_ROOT"
```

两种方式任选其一；`LABSIM_ASSET_ROOT` 优先级高于缓存。它指向包含 `assets/` 的根目录，不是某个 USD 文件或 `assets/lab_cuvette_loading` 子目录。已有完整缓存可使用 `./labsim assets download --offline` 校验复用，不重新联网。`doctor` 是 CPU 预检，不替代 GUI/GPU 或物理验收。

## 演示、采集和评测

省略 `--project-version` 仍调用旧 `Project_v1`。使用本版本的四个运行入口 `demo / eval / collect / serve` 都需明确指定 `Project_v1_1`。相对路径按仓库根目录解析；所有输出目录必须是新目录。

```bash
# 仅查看实际启动参数；不创建输出、不启动仿真
./labsim demo --project-version Project_v1_1 --backend teacher \
  --output outputs/lab_cuvette_loading/Project_v1_1/preview_NEW --dry-run

# 一条 GUI 连续 teacher 示范
./labsim demo --project-version Project_v1_1 --backend teacher --gui \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_NEW

# 固定 standard 场景采集；记录与独立判分流程相同
./labsim collect --project-version Project_v1_1 --backend teacher \
  --episodes 1 --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/collect_NEW

# 同一进程顺序 reset 五集；这是运行命令，不代表已有五次结果
./labsim eval --project-version Project_v1_1 --backend teacher \
  --episodes 5 --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/eval5_NEW
```

固定 standard 使用 `cuvette_xy_1000`（10×10×67.5 mm、20 g 质量假设）、来源槽 A1、F6 蓝色器皿和原 `candidate_far_hinge` A 座；来源架槽宽暂定 16 mm。物理 240 Hz、控制 60 Hz。采集与训练数据保持固定场景，不开展布局 random；其他尺寸只可在独立 demo/eval 使用 `--asset-id` 评估，不能直接继承成功资格。

每次运行的 `summary.json` 汇总逐集结果；`episode_0000/` 内包含 `result.json`、`independent_score.json`、连续 `side_camera.mp4 / wrist_camera.mp4 / dual_view.mp4`，以及 `dataset/episode_0000.h5`、实际动作/状态/接触/事件。等待进程关闭后读取，不打开仍在写入的 H5。完整成功必须有实际松爪、脱指、撤离与后续稳定；到达阶段或返回 `finish` 不等于成功。

已关闭的 `teacher_support_align_01` 保存完整成功及 7,539 个 transition；原 H5 无外部 HDF5 数据依赖，已通过正常 ACT/DP batch 和替代路径读取。见[便携验收](diagnostics/teacher_support_align_01_support_portability_audit/portable_success_acceptance.json)。该 H5 约 1.94 GB，未放入精简阅读包。[固定场景回归及关闭后读取汇总](diagnostics/teacher_standard_v7_closed_data_cohort_01.json)记录五个独立进程的完整成功；相同初态的重复运行不代表一般场景成功概率。这不是跨机器部署或训练验证。

## GPT-6 Astra

后端固定为 Cubence Responses / `gpt-6-astra`；模型推理期间仿真暂停。用当前终端环境提供凭据，禁止写入配置或命令参数。

```bash
read -rsp "Cubence API key: " CUBENCE_API_KEY
export CUBENCE_API_KEY
printf '\n'

./labsim eval --project-version Project_v1_1 --backend gpt6 \
  --episodes 1 --max-calls 160 --headless \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_P4_NEW

unset CUBENCE_API_KEY
```

不传 `--provider-config` 时使用本版本的 `policies/cubence_gpt6.json`：**P4**、最近六个完整工具回合（12 条历史消息）、当前图像最大边 512 / low detail。当前双图、目标说明和标定每次均发送；历史工具回合不包含历史图像。

需要明确选择时，在上述命令中增加一个 `--provider-config`：

- `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4.json`：P4、两个完整回合、512 / low。
- `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high.json`：P4、两个完整回合、640 / high。
- `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high_temporal.json`：显式启用 **P6**，两个完整回合、640 / high，额外附上一不同观测及首次公开双侧接触的腕图，去重后总计最多四图。

- `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail.json`：显式启用 **P7**，一个完整工具回合、当前双图原样保留、固定侧图局部细节及最多一张公开接触历史腕图，总计三至四图。固定裁剪只来自已有 JPEG，不能增加传感器分辨率或物理精度；这是与 P6 分开的组合候选。

- `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view.json`：**P8** 复用 P7 的图像和工具，仅增加通用主动观察提示；在下一局部动作有可见净空依据时换视角再观察，不提供目标坐标、路线或自动动作。见[主动观察说明](public_active_view_p8.md)。

P6/P7/P8 是候选控制提示，不能据 CPU 检查声称完整任务成功。P6 要求入口接触敏感区和接近底部时以最多 100 µm 的下降请求、最多 1 mm/s 再观察；这是模型应遵守的指令，**没有修改通用动作上限、自动阶段、物理或评分**，也不保证实际位移精度。历史接触参考不是有效抓取或承托标签。完整输入、精确 JPEG 与适配边界见[实现说明](public_temporal_visual_context_v1.md)。闭合旧公开帧的一次[观察 QA](camera/temporal_public_qa_d35_plan/README.md)是独立诊断，不是控制任务。

所有配置继续共享上面的旧预算文件，保留已有费用与未知 usage 预留；硬上限为估算 $30 / 1500 网络请求。默认单集最多 160 次逻辑模型调用，超时重试也消耗网络配额；估算不等于供应商账单。先获得真实完整成功后再冻结正式评测，调试、服务错误、物理异常和正式成绩分开。不要创建空账本来重置预算。

## 读取数据及接入 policy

CLI 从 H5 的 `scene_version` 自动选择 `LabCuvetteProjectV11Dataset`。只读取完整关闭的数据，真实成功和有效任务失败分别筛选：

```bash
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_v1_1/collect_NEW/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_v1_1/read_success_NEW.json
```

有效失败改用 `--sample-filter failure` 和新输出文件。`dataset-check` 读取 ACT 与 DP 的实际 batch，不启动训练、不改标签。成功 BC 需同时满足完整任务成功、记录完整性、物理可信和 `success_bc_eligible=true`；服务/执行器/仿真异常不能混入正常任务失败或成功训练索引。不同版本、指纹和图像形状的数据分别建立索引，train/val 按完整 episode 划分。

Python 接入请显式选择新 reader，省略 `dataset_class` 仍是旧 Project_v1：

```python
from scripts.read_lab_cuvette_project_v1_data import read_check
from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset

result = read_check(
    "path/to/closed/episode_0000.h5",
    sample_filter="success", policies=("act", "dp"),
    dataset_class=LabCuvetteProjectV11Dataset,
)
```

动作 `actions[8]` 是七个绝对臂关节目标（rad）加单指位置（m）；完整双指执行目标另存 `control_auxiliary/command_q[9]`，不是将目标当实测状态。原始动作、实际命令、时间和 effort cap 均保留。现有 HF 公开 96 像素小样例仍属于 Project_v1，不能作为本版本样例或与本版本训练混合。

外部 policy 可使用 loopback RPC；单位、动作转换与部署见[适配文档](../../../policy/backends/OPTIONAL_POLICIES.md)：

```bash
./labsim serve --project-version Project_v1_1 --headless --port 8097 \
  --output outputs/lab_cuvette_loading/Project_v1_1/rpc_NEW
```

公开环境接口为 `reset / observe / execute / receipt / status / finish / close`。RPC 没有内置抓取/装载宏；ACT/DP、π0.5、Harness 的新任务性能需各自实际评测，读取 batch 或短程连通不等于完整装载成功。

## 维护入口

`./labsim --help` 与各子命令 `--help` 可查看参数；`--dry-run` 检查路由但不验证物理结果。控制诊断仅用本版本的原生入口 `python -m demos.lab_cuvette_project_v1_1.run --backend diagnostic --probe ...`，不得当作完整任务或训练成功。

代码位置：环境/运行器在 `demos/lab_cuvette_project_v1_1/`，任务在 `tasks/lab_cuvette_loading_project_v1_1.py`，采集器在 `data_collectors/lab_cuvette_project_v1_1_collector.py`，reader 在 `policy/dataset/lab_cuvette_project_v1_1_dataset.py`。保留旧版本及原 CAD/USD，继续在长期 `codex/labsim` 分支迭代；新结果另用输出目录与指纹。完整 cooked 碰撞核查、原生/差分速度差异和真实标定边界仍保留。
