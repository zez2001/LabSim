# LabSim

LabSim 为科学实验机器人提供可重复调用的 Isaac Sim 任务环境。当前主任务是 `lab_cuvette_loading`：Franka 从白色 6×6 来源架取出比色皿，搬运到单台开盖仪器的内部 A 座，完成装载、承托交接、松爪、撤离及至少 3 秒稳定观察。

环境共用物理场景、动作执行器、独立评分和采集器，支持专家示范、图像闭环策略和外部 RPC 策略。任务失败可以是有效评测结果；记录损坏、服务错误与物理异常单独标记。

[English](README_EN.md) · [中文使用入口](README_CN.md) · [开发接入](docs/development/ONBOARDING.md) · [发布版本与验收](docs/lab_cuvette_loading/Project_release_v1/README.md) · [公开资产](https://huggingface.co/datasets/Txie000/SLAI-Labsim)

## 完整演示

[观看完整 teacher 装载视频](docs/lab_cuvette_loading/Project_v1_1/media/teacher_support_align_01_full.mp4)

视频来自 `Project_v1_1` 的同一次实际运行，覆盖来源架初态到撤离后稳定；没有拼接不同尝试。Teacher 使用任务真值，是环境功能验收的参考控制器。GPT 已实际完成稳定抓取、离架和搬运，尚未完成独立装载，不能与 teacher 完整成功混淆。

## 当前支持范围

本轮发布入口为 **`Project_release_v1`**，复用已验证的Project_v1_1物理场景、控制器和评分器，独立增加生命周期、数据闭合与记录模式。当前已完成固定资产检查及短程GUI启动退出；同进程三集和真实外部策略的本轮验收仍在进行，最终状态以[发布验收](docs/lab_cuvette_loading/Project_release_v1/README.md)为准。

| 项目 | 支持内容 | 验证状态 |
|---|---|---|
| 任务与场景 | `lab_cuvette_loading / standard`，完整6×6架、单台仪器、原A座 | 物理基线Teacher全流程已运行；发布版三集待闭合 |
| 资产 | `cuvette_xy_1000`，10×10×67.5 mm，20 g假设质量 | 视觉与碰撞同步派生；未做实物校准 |
| 控制 | 末端或关节动作、接触保持、支撑交接、慢松爪 | 连续IK、动作回执与保护已实测 |
| 策略 | Teacher、Cubence `gpt-6-astra`、外部RPC | GPT真实多轮闭环；其他后端范围见策略文档 |
| 数据 | 双视角RGB、状态、原始/实际动作、接触、事件、时间戳 | 发布版短集H5正常读取通过；连续多集待验收 |
| 评分 | 抓取、清槽、搬运、装载、脱指、撤离、稳定 | 依据实际状态与接触，独立于策略自报 |

物理240 Hz、控制60 Hz。正式采集固定来源槽A1、蓝色器皿F6及相机、布局、光照和物理配置，关闭场景随机化。原座不扩孔；10 mm器皿是独立尺寸假设资产，不改写原12.5 mm资产的配套结论。

## 已验证运行环境

Linux、Python 3.11、Isaac Sim 5.1.0、NVIDIA RTX 4090。运行一个Isaac进程占用一张GPU；同GPU顺序仿真。项目复用既有Isaac和模型环境，不自动升级Isaac、Torch或模型依赖。

现有验收是同一开发机器上的独立checkout和资产缓存验证；没有第二台机器的部署结果。CPU `doctor` 和CI只验证相应契约，不代替GPU物理运行。

## 安装与资产

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --branch codex/labsim https://github.com/zez2001/LabSim.git
cd LabSim
export LABSIM_PYTHON=/absolute/path/to/installed/isaac-python
./labsim assets download
./labsim doctor --json
```

`LABSIM_PYTHON` 必须指向已安装Isaac Sim 5.1的Python 3.11。几何工具使用独立环境，准备方式见[安装与依赖](docs/development/ONBOARDING.md#准备环境与资产)；不要向已有Isaac或策略环境批量安装整个历史`requirements.txt`。

资产固定到HF revision [`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)，匿名下载并校验大小和SHA256。共83个任务依赖文件，其中82个来自HF，一个Franka文件来自固定公共Git LFS来源；不需要HF登录。逐文件来源见[资产锁文件](config/lab_cuvette_loading/Project_v1/assets.lock.json)。

默认缓存为`~/.cache/labsim/assets/<revision>/`；用`LABSIM_ASSET_CACHE`更改缓存根目录，或用`LABSIM_ASSET_ROOT`指定保持`assets/...`结构的完整安装。离线可复用已校验缓存。

## 第一条 demo

显式选择版本，避免进入旧入口。**省略`--project-version`时仍默认`Project_v1`。**

```bash
./labsim demo --project-version Project_release_v1 --sequence early_finish \
  --gui --record-mode eval --output outputs/lab_cuvette_loading/Project_release_v1/gui_001
```

上例是本轮已实际验证的GUI启动、3秒受控交互和正常结束检查，不是完整teacher装载。没有显示桌面时使用`--headless`。完整teacher参考录像见上方；本轮连续任务验收结果单独记录。输出必须为新目录，入口拒绝覆盖旧结果。`--dry-run`只查看命令。

查看`episode_0000/result.json`、`independent_score.json`和`dual_view.mp4`，不要仅凭进程退出码判断成功。原生完整任务约126秒仿真时间，图像采集使墙钟耗时更长。

## 数据采集与读取

```bash
./labsim collect --project-version Project_release_v1 --headless --record-mode collect \
  --sequence teacher early_finish teacher \
  --output outputs/lab_cuvette_loading/Project_release_v1/collect_001

# 必须等待仿真进程完全关闭
./labsim dataset-check \
  --path outputs/lab_cuvette_loading/Project_release_v1/collect_001/episode_0000 \
  --sample-filter success --policy both \
  --output outputs/lab_cuvette_loading/Project_release_v1/collect_001/read_success.json
```

三集命令在同一Isaac进程依次执行teacher、受控提前结束、reset后teacher；本轮正在验收，尚不能把命令本身当作已完成证据。第2集保留失败标签，不进入成功BC。H5保存实际双相机RGB和状态动作；物理基线完整单集约1.94 GB，不包含在小阅读包。`success`只读取合格完整成功，`failure`显式读取有效任务失败，`all_valid`用于明确的数据检查。控制诊断、初始化错误和未完成记录不因可读取而成为成功BC数据。

正常ACT/DP数据动作为8维：7个臂关节绝对位置目标与一个单指位置，实际9维双指执行命令另存。它与末端增量动作含义不同。训练/验证按完整episode划分，本轮仅采集与读取，不运行训练。

[公开可下载样例](config/lab_cuvette_loading/Project_v1/public_samples.json)属于早期`Project_v1`，固定revision `82317fe33089aca5a20827da2adc592a1e0fdddc`，双图缩为96像素、保留完整时间序列；不是新版原生分辨率数据。

记录模式显式使用`--record-mode collect|eval|diagnostic`：collect与eval目前均保存完整H5、原生录像及lossless gzip物理日志；diagnostic保留详细plain日志和额外collector录像。在线评分与安全采样不变。eval当前并非无图像轻量模式；收益以本轮测量为准。

## 零样本评测与外部策略

策略通过同一环境交互，任务失败不代表接口验收失败。外部模型必须明确记录实际推理、动作转换、执行回执和结束原因；模拟客户端或只读一个batch不算模型评测。

- **Cubence gpt-6-astra**：已实际运行多轮图像闭环。最新GPT08稳定抓取与搬运后主动结束，`task_success=false`。本轮不优化提示词或任务成功率，原有预算账本与上限保留。
- **π0.5 / RPent Harness**：使用已有部署与本地RPC，不自动安装模型或下载权重。历史五动作、0.25秒记录仅为短程接入，连续生命周期结果另记。
- **自有策略**：通过`reset / observe / execute / receipt / status / finish / close`。模型等待时物理暂停，动作执行时按约定步数推进。

实际命令、模型依赖和转换语义见[本轮外部策略契约](docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md)与[Project_v1_1策略入口](docs/lab_cuvette_loading/Project_v1_1/README.md)。密钥只存本机凭据或进程环境，不写入仓库、README、日志或数据包。

## Observation 和 Action 契约

[接口与实现地图](docs/development/ONBOARDING.md#策略接口与时序)说明单位、坐标系、限幅、时序和权限。

- 观测包括双RGB、标定、机器人关节/TCP、夹爪状态及声明的器皿过滤指端法向接触模长；没有给策略器皿/目标座真值或评分内部状态。
- 末端动作使用米、弧度、world/TCP参考系及wxyz四元数；关节动作另有各自限制，不能当成相同数值空间。
- 动作携带episode/observation/action ID。旧观测拒绝，同一action ID查询既有回执，不重复运动；部分执行如实记录。
- `GenericContactHold`保持夹爪命令，通过物理接触抓持，不固定器皿。每指驱动力上限不等于实际接触力。
- `finish`只结束当前episode并请求判分；只有实际装载、脱指、撤离和稳定证据才构成任务成功。

## 常见问题

**找不到Isaac或USD**：确认`LABSIM_PYTHON`指向已有Isaac 5.1解释器，再运行`doctor --json`。普通系统Python不会自动成为Isaac环境。

**缺资产或哈希不符**：重新执行`assets download`，或选择完整且已校验的独立资产根目录。不要混用不同revision的USD。

**输出目录存在**：使用新目录。历史失败不会被后来的成功覆盖。

**缺显示环境**：使用`--headless`；GUI运行需要有效桌面显示。CPU预检通过不说明GUI可用。

**GUI退出有扩展错误**：本轮已修复旧菜单销毁顺序触发的`get_stage_state`异常，真实短程GUI退出码为0；仍记录了安装扩展中的`ManipulatorFactory`卸载回调错误，不能说GUI无异常。见[发布版已知问题](docs/lab_cuvette_loading/Project_release_v1/README.md)。

**任务失败但程序正常结束**：查看任务标签、终止原因、记录完整性与物理质量标记。有效失败是可分析结果，环境或服务异常不应伪装为有效任务失败。

## 来源 许可与引用

项目基于[LabUtopia](https://github.com/Rui-li023/LabUtopia)，上游论文、引用和安装说明见[上游文档](docs/upstream/README.labutopia.md)。代码许可见[LICENSE](LICENSE)，第三方资产遵循[锁文件的来源与授权声明](config/lab_cuvette_loading/Project_v1/assets.lock.json)。外部仪器及比色皿CAD的原模型和派生模型已获项目所有者公开授权；Franka文件保留固定公共来源，没有重新上传到HF。

本项目不模拟液体、玻璃破碎、光谱测量或真机操作。实物尺寸、质量、摩擦和动力学尚未真实校准，相关研究边界集中在[版本文档](docs/lab_cuvette_loading/Project_v1_1/README.md)。

## 开发者文档与历史版本

`codex/labsim`是长期开发分支与GitHub默认入口，`main`保留上游基线。日常修复沿用当前分支，独立功能或明确要求时才另建分支；不自动切默认分支或合并整个功能分支。

[开发接入](docs/development/ONBOARDING.md) · [贡献规范](CONTRIBUTING.md) · [CPU CI](https://github.com/zez2001/LabSim/actions/workflows/cpu-contracts.yml) · [结果打包规范](docs/agent_handoff/README.md) · [历史版本](docs/history/README.md)
