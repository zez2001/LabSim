# Project_release_v1 技术参考

**当前推荐使用版本**，任务 `lab_cuvette_loading / standard`。从[项目主页](../../../README.md)或[组内使用指南](../../development/ONBOARDING.md)开始完成安装、完整任务、采集、读取和策略接入。本目录集中记录接口、资产规格及验收证据。

## 当前使用入口

| 文档 | 用途 |
|---|---|
| [组内使用指南](../../development/ONBOARDING.md) | 准备环境 → 完整任务 → 示范采集 → ACT/DP 读取 → 策略 |
| [数据用途与移交](data_usage.md) | 用途成员、success/failure/all_valid 资格、历史 sidecar、外链与 copy |
| [外部策略契约](external_policy/contract.md) | RPC、π0.5/Harness、图像三层处理、任务文本审计 |
| [可选策略部署](../../../policy/backends/OPTIONAL_POLICIES.md) | 已有模型部署与客户端调用 |
| [生命周期技术记录](lifecycle.md) | reset、事务完成、记录模式及历史诊断验收 |

当前示例显式 `--project-version Project_release_v1`；快捷别名 `current` 解析为实际版本名。省略版本保持历史 `Project_v1` 默认。普通完整任务使用 `launch.py`；`run.py --sequence` 用于显式生命周期诊断。

## 资产与物理规格

| 项目 | 当前规格 | 依据 |
|---|---|---|
| 比色皿 | `cuvette_xy_1000`，10×10×67.5 mm；20 g | 原 CAD 外形的统一 XY 尺寸派生；尺寸与质量为工程假设 |
| 来源架 | 白色完整 6×6，槽 A1 取物；F6 蓝色器皿 | 视频对应的参数化架体；16 mm 槽宽为 demo 假设 |
| 仪器 | 单台、开口朝来源架、开盖样品腔 | 外部 CAD 的单位/朝向审计及派生装配 |
| 目标座 | 原内部 A 座 `candidate_far_hinge` | 原几何/尺度和碰撞配置保持；限制净宽约12.6 mm |
| 机器人 | Franka，关节位置目标、连续 Lula IK | 固定来源机器人资产及现有执行器 |
| 步进 | 物理240 Hz / 控制60 Hz | 每控制周期4物理步，接触/动作时间分别记录 |
| 固定场景 | 布局、器皿、机器人初态、相机、光照、物理、判分 | standard冻结配置；采集和训练数据准备无场景随机化 |

[资产锁文件](../../../config/lab_cuvette_loading/Project_v1/assets.lock.json)绑定83文件来源与SHA，HF revision为[`bb880f098180c291f6f65995f969d48047207067`](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)。[尺寸资产注册表](../../../assets/lab_cuvette_loading/Size_v1/registry.json)保留对照与各尺寸变体；当前release固定10 mm资产。视觉与28块壁体碰撞同步派生，空腔及底面保留。具体物理/材质字段由[当前配置](../../../config/lab_cuvette_loading/Project_release_v1/standard.yaml)继承并进入运行指纹。

实物质量、摩擦、机器人动力学和模型接触表示尚待真实校准。当前资产规格服务于刚体仿真装载；12.5 mm原尺寸配套冲突、各历史版本资产及实验结论保留在对应历史记录中。

## 执行与评分规格

完整任务覆盖来源架抓取、清槽、搬运、座内插入、承托、实际脱指、撤离和至少3秒稳定。独立评分使用实际状态与接触证据；策略的 `finish` 只结束当前集并请求评分。

公开动作支持末端与关节控制；空夹爪仿真TCP的跟踪诊断、动作单位/坐标系、限幅及回执定义见[接口与时序](../../development/ONBOARDING.md#策略接口与时序)。Teacher使用任务真值，外部策略观察通过公开facade隔离真值。模型等待时仿真暂停。

最终 `result`、H5、完成标记和发布索引共享完成身份。`record_valid`、`task_success`、记录完整性、物理质量与BC资格分别保存。撤离前终止的 `post_retreat_window` 为 unavailable、稳定结果为null；中止前窗口另称 `terminal_window`。

记录模式 `collect/eval` 保存完整H5、原生视频和gzip物理日志，`diagnostic`保留额外详细日志。用途字段决定数据集合，与记录模式及资格独立，见[数据指南](data_usage.md)。

## 验收记录导航

下列目录保留当时执行提交、原始评分与实际范围。当前正常使用命令以组内指南为准。

| 记录 | 证据 |
|---|---|
| 当前普通Teacher、用途/移交与输入文档回归 | [Internal_use_v1](../Internal_use_v1/20261028/README.md) |
| 原发布说明及当时验收表 | [2026-10-27发布页原文备份](../Internal_use_v1/20261028/previous_guides/Project_release_v1_README.md) |
| 同进程成功—受控结束—成功 | [闭合审计](validation/same_process_collect_01_closed/summary.json) |
| 历史正式ACT/DP 2/1/3读取 | [success](validation/official_dataset_check_clean_4a71635/success.json)、[failure](validation/official_dataset_check_clean_4a71635/failure.json)、[all_valid](validation/official_dataset_check_clean_4a71635/all_valid.json) |
| GUI退出与SDK回调 | [实际退出记录](validation/gui_finish_02_shutdown_actual_20261027/receipt.json) |
| 五类受控终止与权威资格 | [终止审计](validation/termination_cases_01_closed/summary.json)、[字段补充](validation/termination_cases_01_closed/authoritative_fields_addendum.json) |
| 真实π0.5连续策略与闭合数据 | [client](external_policy/pi05_standard_01_client_closed/receipt.json)、[正常读取](validation/pi05_standard_01_env_closed/summary.json) |
| 存储/性能对照 | [同口径比较](validation/baseline_vs_collect_01_comparison/summary.json) |
| 物理与执行器历史基线 | [Project_v1_1](../Project_v1_1/README.md) |

## 已知使用问题

处理步骤集中在[组内指南常见问题](../../development/ONBOARDING.md#常见问题与处理)：SDK退出回调、长批次RSS增长、同机PID保护、任务文本截断及移交缺依赖。CPU预检/CI与GPU运行分别报告；新机器按完整操作流程验收。
