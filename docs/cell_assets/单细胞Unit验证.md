# 单细胞测序 unit 场景与策略验证交接

更新：2026-11-02；执行人：姚俊杰。本轮已获授权推送 GitHub 分支 `codex/labsim_junjie_yao_20261102` 并创建 PR；HF 不更新。发布结果见 [代码复核](代码复核.md)。

## 当天最新任务与执行顺序（2026-11-02）

1. **先 rebase，再开发**：核对上游最新 commit，将现有功能分支 rebase 并解决冲突，保留已有本地工作；不另起重复分支。本轮开发基线记录为 `ab519ed`，不能将其写成未经重新联网核对的实时最新提交。
2. 每个当前可用仪器建立一个“单细胞测序 unit”场景，包含机械臂、仪器及简单任务目标；提供统一调用 API、CLI 和 README，补充现有项目文档。
3. 按当前 LabSim 功能验证 expert 数据生成、数据关闭回读，以及 GPT-6 / π0.5 的真实策略调用与执行；先不做数据采集训练或完整 benchmark。
4. PCR 增加小试管插入孔腔的操作。π0.5 可以失败，但须有明确放置目标和真实手臂动作，不能只展示夹爪开合；expert 初始化必须与模型控制分开标注。
5. 所有简单任务和策略评测视频整合进唯一 HTML 的对应资产卡片，状态、说明、筛选及实际证据保持一致；静态／关节回放、expert 仿真通过、policy 失败和真机验证分别说明。
6. 复用现有工程，清理无用重复代码，避免不必要的防御性代码；更新中文交接 MD 后导出最新代码快照。完整工程只在 `labsim/`，快照只放代码与 `assets/README.md`；最新追加授权为推送 `codex/labsim_junjie_yao_20261102` 并创建 PR，HF 不更新。

本次页面修订：PCR 的卡片和详情标签改为“机械臂插管仿真已验证 · Expert”，同步加入已验证筛选、移出仅关节／待验证筛选。前九类中 5 类已有限定范围的机械臂流程；加上原比色皿基线，页面已验证筛选共 6 项。GPT-6 / π0.5 仍未完成 PCR 插管。此修订仅更新展示和交接，没有新 GPU 运行，原 83 段视频与原始实验记录不变。

## 当前结果

五个独立 unit 均具备 Franka、仪器／架体、明确目标、expert 数据生成、公开动作接口、独立判分与视频。五个 expert 已通过，共 **3990 个 transition**（前四个为已完成证据，本轮新增 PCR 990 个）。policy 采用真实模型推理，没有把 expert 冒充模型动作，当前策略任务均未成功；训练和真机验证未执行。

| unit | Expert | GPT-6 | π0.5 |
| --- | --- | --- | --- |
| `ika_open` | 通过；24 秒 / 720 transitions | 8 次调用 / 15 秒；失败 | 默认初态：53 次 / 261 动作 / 13.05 秒；失败 |
| `diynafluor_uncap` | 通过；21 秒 / 630 transitions | 8 次调用 / 15 秒；失败 | 默认初态：72 次 / 359 动作 / 17.95 秒；失败 |
| `flex_load` | 通过；27.5 秒 / 825 transitions | 8 次调用 / 15 秒；失败 | 放置尝试：11 次 / 52 动作 / 2.58 秒；失败<br>默认初态：120 次 / 600 动作 / 30.00 秒；失败 |
| `magsep_transfer` | 通过；27.5 秒 / 825 transitions | 8 次调用 / 13 秒；失败 | 放置尝试：39 次 / 192 动作 / 9.58 秒；失败<br>默认初态：120 次 / 600 动作 / 30.00 秒；失败 |
| `pcr_insert` | 通过；33 秒 / 990 transitions | 8 次调用 / 15.5 秒；失败 | π0.5：60 次 / 300 动作 / 15.00 秒；失败 |

## π0.5 修正与放置尝试

旧 1 秒评测只有夹爪明显动作，确有控制问题：策略每轴位移限幅 0.5 mm，而 Lula 默认位置容差 1 mm，求解器接受了不变的关节热启动；旧 TCP 最大位移约 0.008 mm。撤回此前以动作接受数判断“机械臂操作连通”的结论，旧证据保留但退出当前 HTML 选择。

现在用有界局部 IK，对实际 FK 误差与关节每步速度／限位检查；测试覆盖亚毫米移动与不可达拒绝。摘要另记录真实末端路径和最大位移，`integration_complete` 要求动作执行且有实际移动，仍不表示任务成功。原 LIBERO 权重与动作坐标／夹爪符号保持不变，未做 LabSim 微调。

Flex / MagSep 新增 `--initial-state placement-ready`：expert 通过真实接触抓取空架、搬到目标上方约 6 cm；随后模型独立负责下放、形成支承后松爪、撤离并稳定。准备段有单独录像和接触记录，不计入 policy 时间、动作数或能力。两次尝试均提前张爪掉落，后续移动产生碰撞，属于失败，不将落在目标附近算作受控放置成功。

- `ika_open` / π0.5 · 默认初态：实际 13.05 秒，末端累计路径 18.6 cm、最大位移 11.1 cm；结束原因 `POLICY_ACTION_REJECTED`。
- `diynafluor_uncap` / π0.5 · 默认初态：实际 17.95 秒，末端累计路径 26.2 cm、最大位移 15.6 cm；结束原因 `POLICY_ACTION_REJECTED`。
- `flex_load` / π0.5 · 放置尝试：实际 2.58 秒，末端累计路径 3.5 cm、最大位移 2.4 cm；结束原因 `UNINTENDED_COLLISION`。
- `flex_load` / π0.5 · 默认初态：实际 30.00 秒，末端累计路径 44.0 cm、最大位移 32.8 cm；结束原因 `POLICY_BUDGET`。
- `magsep_transfer` / π0.5 · 放置尝试：实际 9.58 秒，末端累计路径 17.9 cm、最大位移 9.7 cm；结束原因 `UNINTENDED_COLLISION`。
- `magsep_transfer` / π0.5 · 默认初态：实际 30.00 秒，末端累计路径 44.0 cm、最大位移 27.9 cm；结束原因 `POLICY_BUDGET`。
- `pcr_insert` / π0.5：实际 15.00 秒，末端累计路径 20.3 cm、最大位移 13.2 cm；结束原因 `POLICY_BUDGET`。

默认初态的延长录像也保留在对应卡片作为对照。IKA / DIYNAFLUOR 因动作或关节连续性限位提前终止，Flex / MagSep 默认初态到达 30 秒预算仍未完成任务。初态和任务不同，不混算成功率。

`pi05_motion_audit.json` 对两次放置原轨迹做了 CPU 判分复核：初始夹持取自独立准备记录，而非模型首次张爪后的采样；不要求在放置阶段再次完成拾取抬升。结果仍失败，尤其是“支承后才松爪”未通过。此复核不计为新 GPU 运行，原 result、H5、轨迹与源码指纹未改写。当前代码已采用此初态判分规则。

## PCR 小试管入孔

`pcr_insert` 沿用 ChemLab CFX Opus 外壳与电动滑盖；原贴图孔／实心块在派生场景中替换为有侧壁、有底的 12×8 孔阵列。小管外径 6 mm、总高 26 mm、盖径 8 mm，孔深 12.6 mm；均为明确记录的工程假设，不是厂家 CAD、实测尺寸或认证耗材。原资产缓存未修改，`load_asset` 不会自动变成这个派生版本。

目标改为中央第 4 行、第 6 列，以避免原装夹指与边缘导轨干涉。expert 使用 480 Hz 物理、缓闭合、每指 0.5 N 驱动力上限及物体位姿对齐反馈；不绑定或传送小管，policy 没有物体真值反馈。成功运行 33 秒、15840 物理步，末端撤离后小管插深 12.5999 mm、支承力约 0.00588 N、双指无接触，全部 12 项评分通过。正面、侧面和孔位特写录像均保留。

盖子预先打开，未验证机器人开盖、整板装载、热循环、流体或检测。OpenFlexure 的夹指干涉、Poseidon 仅为辅助支架和三类缺失整机的材料缺口不变。

## 上游同步与代码边界

先将原功能分支 `codex/labsim_junjie_yao_20261027` rebase 到 `origin/codex/labsim` 的 `ab519ed4f2493e5ae069a8b661e6a51e1d432186`（`Project_release_v1`），再开发 unit。rebase 后 HEAD 为 `2294a17`，五个本地提交依次为 `f1e48a1 / ccb4b05 / 548be7d / fb1f830 / 2294a17`。README 冲突保留新上游入口和单细胞资产说明。原未提交的 RM65、环视、基线 HTML 等工作恢复并保留；恢复用 stash 未删除。

旧 PR #1 已关闭；本轮按最新授权在 `codex/labsim_junjie_yao_20261102` 完成最新上游 rebase，随后推送代码并创建新 PR。现场测量、真机验证、训练和完整 benchmark 均未执行。

| 入口 | 职责 |
| --- | --- |
| `config/cell_units/units.json` | unit 名称、仪器、任务目标和阻塞项的唯一注册表 |
| `demos/cell_units/registry.py` | 调用原仪器场景构建器；MagSep 独立场景不加载 Flex |
| `environment.py`、`sensors.py` | 实现当前 release task 协议；真实腕部／侧面相机和状态 |
| `recording.py`、`scorer.py` | 独立 unit H5、逐物理步轨迹、与策略声明无关的物理评分 |
| `policy.py`、`pi05.py` | 复用 GPT 传输／工具和原 π0.5 LIBERO 适配／评测循环 |
| `rpc.py`、`run.py` | 当前 release RPC、统一 CLI、单 GPU 锁、退出记录 |
| `scripts/update_cell_asset_showcase.py` | 将本轮结果和视频追加到对应资产详情，保留原媒体 |

原 `handling.py / hood_open.py / cap_cycle.py` 仅提取共享测量函数并增加场景 driver 回调；默认旧演示流程保留。原任务复用已有场景；PCR 新增任务所需孔腔和小管生成器，不修改源缓存。策略动作由当前 `ProjectEnvironment` 处理 ID、限幅、IK 和回执。原比色皿 Cubence 默认配置和校验保持原行为；unit 通过显式配置使用用户提供的 HTTPS 服务。

## 运行方式

完整参数、Python 示例与接口单位见 [unit README](../../demos/cell_units/README.md)。在 `labsim/` 根目录运行：

```bash
export LABSIM_PYTHON=/home/admin001/miniconda3/envs/labsim/bin/python
./labsim unit list
./labsim unit collect --unit ika_open --headless --output outputs/ika_expert_NEW
./labsim unit dataset-check --path outputs/ika_expert_NEW/episode_0000
./labsim unit serve --unit ika_open --headless --output outputs/ika_rpc_NEW --port 8097
```

把 `--unit` 换成表内 ID 即可调用其他场景。输出目录必须不存在；不覆盖旧实验。RPC 仅监听 loopback，沿用 `POST /call`、`project.* / env.*`，通过 `env.reset` 开始；动作类型为关节位置／速度、TCP 位姿／增量。重复动作 ID 返回同一回执；旧 episode 不能操作 reset 后的新场景。没有 teacher 或真值 RPC。

GPT 使用 `LABSIM_UNIT_API_KEY` 环境变量与不含密钥的 `--provider-config`；不要在代码、参数或文档中写密钥。本机配置位于 `local_setup/cell_units/gpt_provider.json`，密钥文件不属于工程或交付快照。预算账本包括开发失败尝试，未清零；估价沿用上游参考价格，不是该服务商实际账单。

```bash
./labsim unit eval --unit ika_open --backend gpt6 --headless \
  --provider-config local_setup/cell_units/gpt_provider.json \
  --max-calls 8 --output outputs/ika_gpt_NEW

export LABSIM_PYTHON=/home/admin001/miniconda3/envs/labsim-policy/bin/python
./labsim unit eval --unit ika_open --backend pi05 --headless \
  --checkpoint local_assets/policies/RLinf-Pi05-LIBERO-130-fullshot-SFT \
  --max-calls 120 --max-actions 600 --output outputs/ika_pi05_NEW
```

## 模型与环境

原 `labsim` Conda 环境未改动。模型推理使用同级 `labsim-policy` Conda 克隆环境，不在项目里建立虚拟环境。Isaac Sim 5.1，Python 3.11，RTX 4090，驱动 580.178.04；本机完整部署记录在 `local_setup/cell_units/README.md`。

- OpenPI 实现：[RLinf/openpi](https://github.com/RLinf/openpi/tree/c5dc4b9296a1a4739bf52828f28a579f12dce763)，固定提交 `c5dc4b9296a1a4739bf52828f28a579f12dce763`。editable 安装其模型包与 client，并按项目说明在独立环境安装 `transformers_replace`。
- 模型：[RLinf-Pi05-LIBERO-130-fullshot-SFT](https://huggingface.co/RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT/tree/6222623f635769bfc73c9472e29fab9b7fd8e027)，revision `6222623f635769bfc73c9472e29fab9b7fd8e027`；仅下载推理权重和归一化文件。
- 权重 `model.safetensors`：7,473,091,464 bytes，SHA256 `4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683`；`physical-intelligence/libero/norm_stats.json`：SHA256 `dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1`。运行前校验。
- tokenizer：官方 `https://storage.googleapis.com/big_vision/paligemma_tokenizer.model`，SHA256 `8986bb4f423f07f8c7f70d0dbe3526fb2316056c17bae71b1ea975e77a168fc6`；缓存到 `local_assets/policies/openpi-cache/big_vision/`。
- 已运行依赖：torch 2.7.0/CUDA 12.6、jax/jaxlib 0.5.3 CPU、flax 0.10.2、orbax 0.11.13、transformers 4.53.2、pydantic 2.10.6、numpydantic 1.6.8、chex 0.1.90、jaxtyping 0.2.36、beartype 0.19。Isaac 相关约束保留 fsspec/gcsfs 2024.6.1、packaging 23.0、requests 2.32.3。

OpenPI 元数据要求 torch 2.7.1，且包含本轮未安装的 LeRobot／ALOHA 等训练依赖；**不宣称 `pip check` 全部通过**。上述实际推理范围已经运行，训练环境兼容性未验证。采用官方双图输入、量化归一化、10 步去噪与 LIBERO 输出变换；权重没有针对 LabSim 微调。

## 证据与复核

唯一结果目录为 `results/final/unit-validation/`，`index.json` 是当前展示选择，保留每次运行的原始结果、物理轨迹、视频、H5、模型输入输出及源码指纹。当前页面保留原 42 段媒体，当前所选 unit 视频（含两段单独标注的 expert 准备）41 段，共 83 段内嵌视频；17 组有效 episode 对应 5 个 unit。没有生成第二个历史展示页面。

历史 H5 为 `SingleCellUnit_v1`，本轮 IKA／PCR 复验为 v2，读取器兼容两者：观测通常 30 Hz，动作块为 N×stride×9，stride=物理 Hz/30（普通 unit 4；PCR 16），末段补零不执行。成功 expert 和失败 policy 分别标注，所有选中 episode 关闭后通过 `dataset-check` 回读，详见 `dataset_validation.json`。不宣称接入 ACT/DP 训练。

此前针对性 CPU 回归 **203 passed, 1 skipped**：unit 评分（包含禁止高处松爪掉落）、真实亚毫米 IK、孔腔射线和 H5 双频率；另覆盖现有资产、GPT、release 生命周期／RPC／数据、CLI 和快照导出。跳过项为普通 Python 的 pxr 检查。该结果不能代替 GPU 实验。

PCR 早期插孔尝试失败，分别暴露原块的实心碰撞、夹持滑移、边缘导轨干涉等；失败记录保留，不计入成功 expert。一次 PCR π0.5 30 秒预算进程返回 143、未关闭 episode，原因未查明，记录为中断；重新用 15 秒预算运行，不把未关闭录像当成有效完成结果。原先 IKA 的卸载段错误记录仍在 diagnostics 中。

Isaac 使用官方 fast_shutdown，关闭自有 H5／视频后退出，父进程保存真实返回码。完整原生扩展卸载仍未验证；保留原生材料、mimic、viewport 等告警。各次运行有各自源码指纹，不当作同一冻结 benchmark。

HTML 的媒体全量解码、原媒体哈希保留、JS 语法与卡片链接检查记录在 `html_validation.json`；浏览器播放核验状态以该文件为准。本轮代码规范修正、最新 CPU/GPU 复验和 GitHub 交付状态见 [代码复核](代码复核.md)。代码快照由 `python scripts/export_code_snapshot.py` 生成，保留 assets/README.md，排除模型、媒体、结果、环境、密钥和 .git。HF 现有包不包含本轮新 unit 视频／模型权重，不宣称已同步远端。
