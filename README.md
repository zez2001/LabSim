# LabSim

LabSim 是基于 LabUtopia 与 Isaac Sim 的科学实验机器人仿真项目。默认稳定入口为 **`lab_cuvette_loading / Project_v1 / standard`**：Franka 从完整白色 6×6 来源架取出比色皿，搬运到单台开盖仪器的内部 A 座，完成插入、支撑交接、松爪、撤离与至少 3 秒稳定观察。

本地完整工程统一位于 `SLAI_Lab/labsim/`，新增仪器缓存为 `local_assets/`，最终报告与 HTML 在 `results/final/`。每轮验证后运行 `python scripts/export_code_snapshot.py`，生成同级 `codex/labsim_junjie_yao_YYYYMMDD/` 代码交付副本；详见 [交付说明](DELIVERY.md)。

[Project_v1_1 使用入口](docs/lab_cuvette_loading/Project_v1_1/README.md) · [验证报告](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.docx) · [结果阅读包说明](docs/agent_handoff/Project_v1_1_current/00_给Agent阅读说明.md) · [开发分支 `codex/labsim`](https://github.com/zez2001/LabSim/tree/codex/labsim) · [公开资产](https://huggingface.co/datasets/Txie000/SLAI-Labsim) · [开发接入](docs/development/ONBOARDING.md) · [历史实验](docs/history/README.md)

[观看 Project_v1_1 完整 teacher 演示](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_full.mp4) · [松爪与撤离近景](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_release_wrist_clip.mp4)

以上视频来自 Project_v1_1 同一次连续 teacher 运行，完整执行至撤离后稳定；近景标明其局部时间段。teacher 可完成全流程；GPT 已验证稳定抓取和搬运，尚未完成独立装载、释放与撤离。

## 提供的能力

- **同一物理任务，多种控制入口**：真值专家 `teacher`、Cubence `gpt-6-astra` 的图像闭环 `gpt6`，以及供既有 π0.5 / RPent Harness 使用的本地 RPC；任务、记录器和独立评分共用。
- **真实刚体接触**：动态空心比色皿、28 块壁体碰撞、双指接触锁存、支撑交接与缓慢释放。锁存夹指命令，不把器皿绑定到机器人。
- **采集与读取**：侧视和腕视 RGB、关节状态、原始及实际动作、力限制、时间戳、接触、物体状态与阶段；正常 ACT / Diffusion 读取器分别筛选合格成功和失败，当前工作不包含模型训练。
- **可追溯资产**：原仪器内部座保持不变，35 个横向尺寸变体独立注册；新发布资产通过固定 HF revision、大小和 SHA256 校验下载，支持缓存及离线复用。
- **独立判分**：实际取物、清槽、搬运、正确装载、双指脱离、撤离及稳定均需证据。进程退出、控制器阶段或模型的 `finish` 请求不能代替成功。

标准场景固定为 **10×10×67.5 mm** 比色皿、20 g 质量假设、来源槽 A1、F6 蓝色器皿、原内部 A 座 `candidate_far_hinge`；物理 240 Hz，控制 60 Hz。来源架 16 mm 槽宽及材料参数包含工程假设，未做实物校准。原 12.5 mm 器皿与原座的配套结论保留。

## 环境与第一次运行

运行基线为 **Linux、Python 3.11、Isaac Sim 5.1、NVIDIA GPU**，已使用 RTX 4090。同一 GPU 顺序运行仿真。项目不自动升级 Isaac、Torch 或现有模型环境。

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim

# 选择已经安装 Isaac Sim 5.1 的 Python 3.11
export LABSIM_PYTHON=/absolute/path/to/isaac-python
# 如未准备独立几何工具环境，只在新目录安装 Shapely
"$LABSIM_PYTHON" -m venv "$HOME/.local/share/labsim/geometry"
"$HOME/.local/share/labsim/geometry/bin/python" -m pip install --no-deps "shapely==2.2.0"

./labsim assets download
./labsim doctor
./labsim demo --task lab_cuvette_loading --scene standard --backend teacher \
  --gui --output outputs/lab_cuvette_loading/Project_v1/demo_001
```

首次运行前准备依赖的方法见[接入指南](docs/development/ONBOARDING.md)。`LABSIM_PYTHON` 选择既有解释器；几何工具默认发现上述独立目录，也可用 `LABSIM_GEOMETRY_SITE` 选择其他 site-packages，避免向 Isaac 或模型环境安装几何工具。USD / PhysX 扩展从所选 Isaac 安装中发现，不要求 checkout 位于原开发者的目录。

资产默认写入 `~/.cache/labsim/assets/<revision>/`，完整校验后被入口自动采用。可用 `LABSIM_ASSET_CACHE` 更改缓存根目录，或用 `LABSIM_ASSET_ROOT` 指定保持 `assets/...` 布局的完整安装目录。下载不需要 HF 登录。

固定资产 revision 为 [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)。任务依赖包括 82 个 HF 文件和 1 个固定公共 Git LFS 来源的 Franka 文件，共 83 个文件、31,955,703 字节。Franka 的再分发许可尚未核实，没有重新上传到 HF；逐文件来源、授权及哈希见[资产锁文件](config/lab_cuvette_loading/Project_v1/assets.lock.json)。已完成空缓存、无凭据独立进程的 83/83 下载及离线复用检查，见[匿名下载摘要](docs/lab_cuvette_loading/Project_v1/assets/anonymous_download_summary.json)。

省略版本时继续运行 Project_v1。当前独立开发版本 **Project_v1_1** 提供连续 IK、动作回执与运行时保护；必须显式选择，历史版本保持原样：

```bash
./labsim demo --project-version Project_v1_1 --backend teacher \
  --output outputs/lab_cuvette_loading/Project_v1_1/demo_NEW --dry-run
```

去掉 `--dry-run` 后可用 `--gui` 实际运行示范，或使用 `collect / eval / serve` 同样显式选择版本。[Project_v1_1 使用入口](docs/lab_cuvette_loading/Project_v1_1/README.md)集中说明独立缓存、采集、显式版本、可选观测配置、共享预算和正常 reader；下面省略版本的历史示例仍属于 Project_v1。完整物理与 GPT 回归以各版本的实际证据为准。

所有输出目录必须是新目录。无桌面显示时将 `--gui` 换为 `--headless`；可先加 `--dry-run` 查看启动命令。`doctor` 只做 CPU 预检，不等同于 GPU、GUI 或物理任务通过。

## 示范、重复评测与采集

```bash
# 一次完整 headless 示范
./labsim demo --task lab_cuvette_loading --scene standard --backend teacher \
  --headless --output outputs/lab_cuvette_loading/Project_v1/demo_headless_001

# 同一 Isaac 进程连续 reset 并运行 5 集
./labsim eval --task lab_cuvette_loading --scene standard --backend teacher \
  --episodes 5 --headless --output outputs/lab_cuvette_loading/Project_v1/teacher5_001

# 新采集；同样保存完整双视角 episode
./labsim collect --task lab_cuvette_loading --scene standard --backend teacher \
  --episodes 1 --headless --output outputs/lab_cuvette_loading/Project_v1/collect_001

# 动作偏差：插入到 5 mm 后提前停止，不释放、不伪造成功
./labsim collect --task lab_cuvette_loading --scene standard --backend teacher \
  --controlled-stop-depth-mm 5 --headless \
  --output outputs/lab_cuvette_loading/Project_v1/controlled_failure_001
```

`summary.json` 保存逐集结果；`episode_0000/result.json` 与 `independent_score.json` 保存独立判分，`side_camera.mp4`、`wrist_camera.mp4`、`dual_view.mp4` 是同次运行的连续录像。该 episode 的 `dataset/episode_0000.h5` 保存图像与状态，物理、接触及任务事件另存。成功的一集约需 106 秒仿真时间，图像记录使墙钟运行明显更长。

Project_v1 默认保持 standard；采集、训练及训练内自动验证关闭场景随机化。历史 Size_v1 配额采集与审计仍可显式使用 `collect --phase ...` / `validate`，见[原任务说明](demos/lab_cuvette_size_v1/README.md)；旧冻结资格不自动赋予 Project_v1。

尺寸变体可在独立 demo / eval 中用 `--asset-id cuvette_xy_1030` 选择，也可在独立 YAML 中只设置 `asset_id`。入口会同时更新视觉/碰撞引用、尺寸、质量属性和注册哈希，不自动移动目标轴或改变原座。几何预检及物理成功仍需重新验证；正式 `collect` 固定使用 `cuvette_xy_1000`。

## GPT-6 Astra 图像闭环

新版 GPT 控制显式选择 `Project_v1_1`，提供连续 IK、实测动作回执、运行时保护和指端接触保持；完整任务能力按实际独立判分记录。直接后端固定使用 Cubence `https://api.cubence.ai/v1` 和 `gpt-6-astra`，不修改全局 Codex 配置，也不回退到其他模型。在当前终端读取密钥，避免写入 shell 历史、仓库或日志：

```bash
read -rsp "Cubence API key: " CUBENCE_API_KEY
export CUBENCE_API_KEY
printf '\n'

./labsim eval --project-version Project_v1_1 --task lab_cuvette_loading --scene standard --backend gpt6 \
  --episodes 1 --max-calls 160 --headless \
  --provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view_self_state.json \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_attempt_001

unset CUBENCE_API_KEY
```

[提供方配置](config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6.json) 声明 Responses API、超时、动作限制和估算价格。探针、重试及评测应共用同一预算 ledger；默认硬上限为 **估算 $30 / 1500 次网络请求**，单集默认最多 160 次模型调用。估算费用不等于供应商账单。Project_v1_1 继续共用上述 ledger，保留已有请求和费用占用；先获得完整成功再冻结并运行新版正式五次，不用空 ledger 重置预算。

需要比较历史上下文配置时，可用 `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4.json` 替换上例的 `--provider-config` 参数值。该独立配置保留最近两个完整工具回合，每一步仍发送当前双图、目标说明、机器人状态和相机标定；其他提供方设置及预算上限不变。兼容默认 P4 保留最近六个回合，不能把不同配置的调试与正式成绩混算。详细命令和验收范围见[新版使用入口](docs/lab_cuvette_loading/Project_v1_1/README.md)。

省略 `--provider-config` 时保持兼容的 P4 / 512 low 配置。上例显式选择 P9：640 high 双图、固定规则侧部细节图、公开历史腕图，以及从公开关节和 TCP 推导的机器人自身连杆坐标。连杆包络只描述机器人输入几何，不能证明障碍净空。模型仍自行选择通用动作，配置没有自动路线或任务宏。[观测配置与实际验收范围](docs/lab_cuvette_loading/Project_v1_1/README.md)区分默认配置、各候选及真实失败；近座 100 µm 动作提示不构成精度或成功保证。

GPT 读取两路 RGB、相机标定、机器人状态及允许的指端接触信号，通过通用末端移动、夹爪、等待和结束请求控制；没有专家装载宏、器皿真值位姿或评分内部状态。模型请求期间仿真暂停，执行后产生新观测。过期观测被拒绝，同一动作 ID 查询已有回执，不重复运动。完整成功仍由物理结果判定，API 连通或短动作序列不能当作完成任务。运动工具默认每指 8 N 驱动上限，夹爪工具可显式选择 0–8 N；逐动作保存上限，实测接触力另记。

可选 π0.5 / Harness 通过 `./labsim serve` 接入，部署与有限预算调用见[策略适配说明](policy/backends/OPTIONAL_POLICIES.md)。历史 Project_v1 各实际执行了 5 个动作、0.25 秒仿真的短程连通回归；均未完成完整装载。依赖不自动安装。

## 读取数据与接入策略

等待仿真进程退出后，通过正常读取器验证 batch：

```bash
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_v1/collect_001/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_v1/collect_001/read_success.json
```

失败 episode 使用 `--sample-filter failure` 和新的输出文件。读取不启动训练，也不改标签。`dataset-check` 按 H5 的 `scene_version` 自动选择独立 reader；`control_diagnostic` 不能进入成功 BC。单集 H5 保存实际图像和状态；多集索引若使用相对链接，传输时保留其 collection 树。

公开完整成功样例约 284 MB，保留全部 6,348 个 transition；两路 RGB 缩为 96 像素，其余数值轨迹保留。使用独立安装的 HF CLI，无需登录即可下载；目录必须另选未使用的路径：

单细胞前流程设备见[设备资产与 API](demos/cell_assets/README.md)：固定版本下载并加载 PCR、移液工作站、恒温摇床、磁珠分离架体及 DNA 定量仪、细胞计数器打印件装配，另含 Poseidon 固定显微支架辅助资产，提供 Franka 的 IKA 装载／开关盖、DIYNAFLUOR 取帽／停放／盖回及 Flex／MagSep 架体装载／取回接触示例，[本地交接汇报](docs/cell_assets/交接汇报.md) 汇总当前状态。大型源模型和运行结果存放在项目外；类别替代、机构验证范围、许可和未覆盖设备见该文档。

```bash
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 hf download Txie000/SLAI-Labsim \
  --repo-type dataset --revision 82317fe33089aca5a20827da2adc592a1e0fdddc \
  --include 'examples/Project_v1_teacher_gui_01/*' --local-dir public_sample_001
./labsim dataset-check \
  --path public_sample_001/examples/Project_v1_teacher_gui_01/episode.h5 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_v1/public_sample_read_001.json
```

文件 SHA256 和来源版本见[样例索引](config/lab_cuvette_loading/Project_v1/public_samples.json)。该样例来自早期 Project_v1 GUI 版本，与后续正式评测指纹分开，不能直接合并训练。上述 HF CLI 命令已在隔离凭据目录实际匿名下载并逐文件核验。

公开小样例若声明为 96 像素图像派生版，`dataset-check` 按 H5 实际 RGB 形状读取并报告派生信息；正式训练配置仍为 256 像素，不能把缩图样例当作原生 256 像素数据。

Project_v1_1 的成功 H5 已有自含数据依赖及替代路径正常 ACT/DP 读取证据，见[便携验收](docs/lab_cuvette_loading/Project_v1_1/diagnostics/teacher_support_align_01_support_portability_audit/portable_success_acceptance.json)。CLI 根据版本自动路由新 reader；Python 直接调用须显式传 `LabCuvetteProjectV11Dataset`，不要套用旧版本的筛选规则。约 1.94 GB 的原完整 H5 不收入精简阅读包，也不将该证据称为异机部署或模型训练验证。

[Project_v1 ACT](policy/config/task/lab_cuvette_project_v1_act.yaml) / [DP 配置](policy/config/task/lab_cuvette_project_v1_dp.yaml) 直接使用 `side_camera_rgb`、`wrist_camera_rgb`，不需旧相机名称 override。读取器只接受同一指纹的 Project_v1 standard 完整任务；成功 BC 默认只读合格成功，失败用于显式选择的分析或学习方法，train / val 按完整 episode 划分。

公开机器人接口为 `ProjectEnvironment.reset / observe / execute / receipt / status / finish / close`。ACT / DP 的 8 维数据动作是 7 个臂关节位置目标加一个对称夹指位置；实际执行的 9 维双指命令另存。ACT / DP 的输出通过 `policy.backends.action_adapters.act_dp_joint_action` 转换：第八维为单指位置，转换为双指总开口。GPT / π0.5 末端动作明确区分米、弧度、world / TCP 参考系和 wxyz 四元数。接口与代码地图见[接入指南](docs/development/ONBOARDING.md)。

## 验证证据与限制

历史 Size_v1 已完成固定配置 5/5 验证及 20 条合格完整成功、20 条受控提前停止失败；这些失败不是自然卡滞。既有完整物理任务链已再次复现。历史结果与录像见[尺寸实验报告](docs/lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.md)，不能直接当作 Project_v1 新入口或 GPT 成功率。

Project_v1 同机干净 checkout 已完成一次 GUI 全流程，以及该版本入口的 **5/5 headless 连续 reset 完整成功**；新采集的一条受控失败和五条成功均通过正常 ACT/DP 读取。GPT 已实测真实多轮图像闭环，冻结配置正式五次中 **没有完整成功**：一条有效抓持滑移失败、四条碰撞或控制异常终止；调试中的离架事件没有计为搬运成功。[Project_v1 发布与验证报告](docs/lab_cuvette_loading/Project_v1/report/LabSim_Project_v1_项目发布与验证报告.md)提供逐集结果、录像、版本和预算，不能将这些固定初态重复当作广泛场景成功概率。

Project_v1 发布、匿名资产验证和该版本执行证据集中在 [Project_v1 文档目录](docs/lab_cuvette_loading/Project_v1/)。GPU 完整运行、策略完整任务和数据读取以实际保存的结果为准。代码仓库不包含历史约 61 GB 原始 collection，也不因公开资产而发布凭据、模型权重或完整训练数据。

未做实物尺寸、质量、摩擦及机器人动力学校准；保留原生速度与位姿差分不一致等物理质量告警。静态原座的完整有效 PhysX 烹饪表示尚未全部读回。输入几何抽样不能证明严格全局穿透上界，也不能解释为 0.1 mm 真实精度认证。本项目不包含液体、玻璃破碎、光谱测量或真机操作。

## 常见问题

- `doctor` 找不到 Isaac 或 USD：将 `LABSIM_PYTHON` 指向已安装 Isaac Sim 5.1 的 Python 3.11，再运行 `doctor --json`；普通系统 Python 不会自动成为 Isaac 环境。
- Shapely 接口缺失：按接入指南新建独立几何工具环境，或设置 `LABSIM_GEOMETRY_SITE`，不升级现有 Isaac / 模型环境。
- 资产缺失或 SHA 不符：执行 `./labsim assets download` 重新获取声明文件；离线模式需要此前完整校验的缓存。不要手工把不同版本 USD 混进同一缓存。
- 输出目录已存在：选择新的目录，入口会拒绝覆盖旧结果。GUI 缺少显示环境时使用 `--headless`。
- GPT 缺凭据、超时或返回模型不符：检查当前进程的环境变量和 provider 配置；错误会保留在本次独立目录，不会替换模型、接管任务或伪造成功。统计结果时分别查看任务结果与服务/协议/物理错误。

## 开发与来源

`codex/labsim` 是长期开发分支，`main` 保留上游基线。日常修复沿用当前分支，独立功能再建短期分支。修改场景、控制、评分或资产需建立新配置/数据指纹，保留历史文件。完成验证后提交、推送并建立本轮精简阅读包，见 [CONTRIBUTING.md](CONTRIBUTING.md) 与[打包说明](docs/agent_handoff/README.md)。

GitHub [CPU contracts](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml) 检查接口及评分等 CPU 契约；GPU 物理运行另记。项目基于 [LabUtopia](https://github.com/Rui-li023/LabUtopia)，上游说明见[上游文档](docs/upstream/README.labutopia.md)。代码许可见 [LICENSE](LICENSE)，第三方资产适用各自声明。项目背景见[背景文档](docs/background/README.md)。
