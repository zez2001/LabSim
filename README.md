# LabSim

LabSim 是基于 LabUtopia 与 Isaac Sim 的科学实验机器人仿真项目。当前入口为 **`lab_cuvette_loading / Project_v1 / standard`**：Franka 从完整白色 6×6 来源架取出比色皿，搬运到单台开盖仪器的内部 A 座，完成插入、支撑交接、松爪、撤离与至少 3 秒稳定观察。

[开发分支 `codex/labsim`](https://github.com/zez2001/LabSim/tree/codex/labsim) · [公开资产](https://huggingface.co/datasets/Txie000/SLAI-Labsim) · [开发接入](docs/development/ONBOARDING.md) · [历史实验](docs/history/README.md)

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
# 选择独立的 Shapely>=2.1 Python3.11 site-packages
export LABSIM_GEOMETRY_SITE=/absolute/path/to/geometry/lib/python3.11/site-packages

./labsim assets download
./labsim doctor
./labsim demo --task lab_cuvette_loading --scene standard --backend teacher \
  --gui --output outputs/lab_cuvette_loading/Project_v1/demo_001
```

首次运行前准备依赖的方法见[接入指南](docs/development/ONBOARDING.md)。`LABSIM_PYTHON` 选择既有解释器；`LABSIM_GEOMETRY_SITE` 避免向 Isaac 或模型环境安装几何工具。USD / PhysX 扩展从所选 Isaac 安装中发现，不要求 checkout 位于原开发者的目录。

资产默认写入 `~/.cache/labsim/assets/<revision>/`，完整校验后被入口自动采用。可用 `LABSIM_ASSET_CACHE` 更改缓存根目录，或用 `LABSIM_ASSET_ROOT` 指定保持 `assets/...` 布局的完整安装目录。下载不需要 HF 登录。

固定资产 revision 为 [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)。任务依赖包括 82 个 HF 文件和 1 个固定公共 Git LFS 来源的 Franka 文件，共 83 个文件、31,955,703 字节。Franka 没有重新上传到 HF；逐文件来源、授权及哈希见[资产锁文件](config/lab_cuvette_loading/Project_v1/assets.lock.json)。已完成空缓存、无凭据独立进程的 83/83 下载及离线复用检查，见[匿名下载摘要](docs/lab_cuvette_loading/Project_v1/assets/anonymous_download_summary.json)。

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

## GPT-6 Astra 图像闭环

直接后端固定使用 Cubence `https://api.cubence.ai/v1` 和 `gpt-6-astra`，不修改全局 Codex 配置，也不回退到其他模型。在当前终端读取密钥，避免写入 shell 历史、仓库或日志：

```bash
read -rsp "Cubence API key: " CUBENCE_API_KEY
export CUBENCE_API_KEY
printf '\n'

./labsim eval --task lab_cuvette_loading --scene standard --backend gpt6 \
  --episodes 1 --max-calls 160 --headless \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1/gpt_attempt_001

unset CUBENCE_API_KEY
```

[提供方配置](config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json) 声明 Responses API、超时、动作限制和估算价格。探针、重试及评测应共用同一预算 ledger；默认硬上限为 **估算 $30 / 1500 次网络请求**，单集默认最多 160 次模型调用。估算费用不等于供应商账单。

GPT 读取两路 RGB、相机标定、机器人状态及允许的指端接触信号，通过通用末端移动、夹爪、等待和结束请求控制；没有专家装载宏、器皿真值位姿或评分内部状态。模型请求期间仿真暂停，执行后产生新观测。过期观测被拒绝，同一动作 ID 查询已有回执，不重复运动。完整成功仍由物理结果判定，API 连通或短动作序列不能当作完成任务。

可选 π0.5 / Harness 通过 `./labsim serve` 接入，部署与有限预算调用见[策略适配说明](policy/backends/OPTIONAL_POLICIES.md)。这些依赖不自动安装，也不等同于已完成新任务的策略评测。

## 读取数据与接入策略

等待仿真进程退出后，通过正常读取器验证 batch：

```bash
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_v1/collect_001/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_v1/collect_001/read_success.json
```

失败 episode 使用 `--sample-filter failure` 和新的输出文件。读取不启动训练，也不改标签。单集 H5 保存实际图像和状态；多集索引若使用相对链接，传输时保留其 collection 树。

[Project_v1 ACT](policy/config/task/lab_cuvette_project_v1_act.yaml) / [DP 配置](policy/config/task/lab_cuvette_project_v1_dp.yaml) 直接使用 `side_camera_rgb`、`wrist_camera_rgb`，不需旧相机名称 override。读取器只接受同一指纹的 Project_v1 standard 完整任务；成功 BC 默认只读合格成功，失败用于显式选择的分析或学习方法，train / val 按完整 episode 划分。

公开机器人接口为 `ProjectEnvironment.reset / observe / execute / receipt / status / finish / close`。ACT / DP 的 8 维数据动作是 7 个臂关节位置目标加一个对称夹指位置；实际执行的 9 维双指命令另存。GPT / π0.5 末端动作明确区分米、弧度、world / TCP 参考系和 wxyz 四元数。接口与代码地图见[接入指南](docs/development/ONBOARDING.md)。

## 验证证据与限制

历史 Size_v1 已完成固定配置 5/5 验证及 20 条合格完整成功、20 条受控提前停止失败；这些失败不是自然卡滞。既有完整物理任务链已再次复现。历史结果与录像见[尺寸实验报告](docs/lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.md)，不能直接当作 Project_v1 新入口或 GPT 成功率。

Project_v1 发布、匿名资产验证和本轮执行证据集中在 [Project_v1 文档目录](docs/lab_cuvette_loading/Project_v1/)。GPU 完整运行、策略完整任务和数据读取以实际保存的结果为准。代码仓库不包含历史约 61 GB 原始 collection，也不因公开资产而发布凭据、模型权重或完整训练数据。

未做实物尺寸、质量、摩擦及机器人动力学校准；保留原生速度与位姿差分不一致等物理质量告警。静态原座的完整有效 PhysX 烹饪表示尚未全部读回。输入几何抽样不能证明严格全局穿透上界，也不能解释为 0.1 mm 真实精度认证。本项目不包含液体、玻璃破碎、光谱测量或真机操作。

## 开发与来源

`codex/labsim` 是长期开发分支，`main` 保留上游基线。日常修复沿用当前分支，独立功能再建短期分支。修改场景、控制、评分或资产需建立新配置/数据指纹，保留历史文件。完成验证后提交、推送并建立本轮精简阅读包，见 [CONTRIBUTING.md](CONTRIBUTING.md) 与[打包说明](docs/agent_handoff/README.md)。

GitHub [CPU contracts](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml) 检查接口及评分等 CPU 契约；GPU 物理运行另记。项目基于 [LabUtopia](https://github.com/Rui-li023/LabUtopia)，上游说明见[上游文档](docs/upstream/README.labutopia.md)。代码许可见 [LICENSE](LICENSE)，第三方资产适用各自声明。项目背景见[背景文档](docs/background/README.md)。
