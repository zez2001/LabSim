# V0_demo02 判分语义与数据接口核查

日期：2026-10-20。本目录是读取既有记录的新分析证据，不是 V0_demo02 新物理轨迹。未运行新场景仿真、训练或优化器。

最终代码与当前场景关口的核查见 [final_contract_checks.json](final_contract_checks.json)。未知来源槽和目标座ID不能因 `null == null` 通过绑定检查；缺独立几何时成功与数据资格保持关闭。目录内较早检查文件是各轮代码快照，当前文件哈希与汇总见 [manifest.json](manifest.json)，历史轨迹和原评分未改。

## 已实际执行

1. 用 `demos/lab_cuvette_demo02/analyze.py` 只读回算 V0_demo01 seed7000 失败记录，并核查固定配置 fixed_0 成功记录的窗口语义。原评分、H5、动作和物理记录未修改。
2. 用 `demos/lab_cuvette_demo02/data_check.py` 检查历史失败 H5 的实际数组、时间对齐和新版本过滤规则；生成只含外链的独立索引。
3. 对空的新任务索引实际调用已有 `policy.dataset.minimal_pick_dataset.MinimalPickDataset`。加载器按预期拒绝：`Dataset contains no complete successful episodes`。没有用旧工程演示冒充新任务样本，也没有生成训练 batch。
4. 执行元数据正例及五种反例接口检查，以及真实历史记录的窗口检查。元数据正例只是程序接口输入，不是合成物理轨迹或成功数据集。

## seed7000 修正语义

历史记录在 OPEN 阶段、46.233333 秒停止，没有执行 RETREAT 或 VERIFY。器皿源几何观察到最大穿透 0.050289093 mm，超过原 0.050000 mm 工程门槛。没有调整该门槛，也没有重标物理成功。

- `post_retreat_window.available=false`，`status=unavailable`。
- `stable_after_retreat=null`，`actual_retreat_clearance_m=null`。
- `terminal_window` 保存中止前最后三秒的真实观察。它不代表完成了撤离或稳定验收。
- 旧 `independent_score.json` 中的 `final_window` 及 `actual_retreat_clearance_m=-0.0137352109` 原样保留在嵌入的原评分中；后者是最后时刻 TCP 到物体顶部的竖直差，并非已完成撤离的几何净空。
- 原工作流失败和 PHYSICS_INVALID_GEOMETRY 不变。

`seed7000_semantics_v2.json` 是新版分析，`demo01_fixed0_semantics_v2.json` 是实际有 VERIFY 和三秒观察的历史对照。两者都不能进入 V0_demo02 的成功数据索引。`semantic_regression_checks.json` 记录原文件哈希、检查结果和脚本哈希。

## 新任务资格与缺测处理

新判分分别输出场景对应验收、连续流程结果、原 CAD 配套验证、真实校准状态和数据资格。原 CAD 配套与真实校准不会因场景或仿真流程通过而自动变为 true。

新分析需要 `scene_contract.json`：版本、资产清单 SHA256、完整来源架对应证据、指定来源槽 ID、腔内目标座 ID、内部座身份、几何通过证据、原生配套及真实校准标志、运行中未绑定或运动学化的审核证据。几何不通过或身份未确认时，场景和成功数据资格保持关闭。

每步 `independent_geometry` 需要从独立源网格/碰撞/坐标检查得到以下实测量，不能把控制器阶段标志当作这些测量：

- `source_slot_id`、`target_seat_id`。
- `source_supported_inside_designated_slot`：初态实际在指定槽内受支撑。
- `source_clearance_m`：器皿最低外轮廓越过来源槽口的实际净空。
- `depth_m`、`bottom_signed_gap_m`、`inside_checked_target_void`：实际腔内目标的深度、底部间隙及几何包含检查。
- `robot_to_vessel_clearance_m`：撤离后整只手爪与器皿的几何净空，不是 TCP 高差。
- `forbidden_robot_environment_contact`：实际全机器人/场景接触审核。

未提供这些独立几何证据，不能通过新任务判分。该接口尚不等于已经实现并验证任意 CAD 的全局穿透算法；完整架、腔内座和几何关口未通过时，不能用参数化空腔代填结果。

VERIFY 表示控制器报告撤离完成，独立判分还核查实际手爪净空、双指实际张开、接触脱离和至少三秒观察。只有进入 RETREAT 不足以产生 post_retreat_window；只有观察不足三秒时，稳定结果仍为 null。对 V0_demo02，即使控制器进入 VERIFY，若独立手爪净空缺测或不足，也只保留 `controller_verify_window`，post_retreat_window 仍 unavailable、stable_after_retreat 仍 null。此反例用实际历史 fixed_0 数据执行，见 `semantic_final_clearance_checks.json`。中止前窗口始终单独命名 terminal_window。

原生线/角速度、USD 原始速度和 COM/姿态差分继续保留。新分析按实际相邻时间戳计算差分，第一个样本的差分不可用，不补零冒充测量。原生非有限值不能通过；有限但与位姿差分不一致作为保留告警，不能单独永久阻止释放。

## H5 采集与索引约定

沿用现有 collector 和 `MinimalPickDataset`，不新增训练框架。新 collector 应写入：

- `scene_version=V0_demo02`，`task=lab_cuvette_loading_V0_demo02`。
- `source_slot_id`、`target_seat_id`、`target_is_internal_chamber`、`asset_manifest_sha256`。
- `data_scope=lab_cuvette_loading_V0_demo02_simulation`，`phase_names_json` 为十一阶段顺序。
- `action_semantics=absolute_7_arm_rad_and_symmetric_finger_metre`：7 个机械臂关节绝对目标（rad）和一个对称手指位置目标（m）。
- `observation_alignment=obs_before_action; next_state_after_explicit_substeps`。
- `success` 和 `complete` 以及独立评分，不得只因控制器进入末阶段就写成功。

`demos/lab_cuvette_demo02/collector.py` 新增 `Demo02Collector`，继承 demo01 collector，保持原来的观测/动作及诊断数组写入方式。它不替换任何旧 collector，也不打开旧 H5 修改。未知槽位和座位 ID 不写成假 ID，原始 null 保留在 scene_contract_json；开始时所有成功/数据资格为 false。

终止顺序为：保存本次 physics_records/events/result，flush H5，运行新独立分析生成新 sidecar，再调用 `collector.finish_episode(result, independent_score=sidecar_path)`。finish 只接受同 episode、相同资产和槽位、相同末状态时刻、匹配物理记录与事件哈希、全部必需独立检查通过的 sidecar。缺少 score、旧版本 score、控制器单独返回 WORKFLOW_SUCCESS、缺少场景对应或缺少物理几何证据，都不能打开 success/data_eligible。原 controller status 仍保留，不因资格判定篡改。

`collector_interface_final_checks.json` 为最终纯元数据/终止资格函数检查：包含完整接口输入正例，以及未知 ID、缺独立判分、历史 score、缺检查项、错误末时刻和机外目标等拒绝反例。没有调用 begin_episode、没有创建假成功 H5，没有生成物理数据。此前接口迭代的检查文件仍保留，最终文件含三个代码模块的 SHA256。

检查包含双路 RGB `[T,3,256,256] uint8`、机器人 `[T,9]`、策略状态和动作 `[T,8]`、时间戳单调与 1/60 秒动作保持、相邻 obs/next 机器人和物体状态连续性、阶段编码与身份绑定。RGB 内容的真实曝光时刻未单独测量，不能把时间戳检查称为相机时延标定。

只在原 H5 complete/success、新独立 score data_eligible、全部必需独立检查、正确版本/场景/身份和数组检查同时通过时，索引才引用该文件。score 必须指向同一个 episode，且 SHA256 与 H5 保存的实际终止判分一致。索引通过 HDF5 external links 只读原数组，不重写原 H5，不把失败或旧工程轨迹的 success 设为 true。索引依赖本机原 H5 路径，精简阅读包不包含完整原数据。

## 复现命令

在仓库根目录、现有 LabUtopia Python 环境中执行。输出路径必须是新的路径，工具拒绝覆盖旧分析。

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo02.analyze \
  outputs/lab_cuvette_loading/V0_demo01/random3_20261019/seed_7000/trial_00 \
  --historical --output /tmp/seed7000_semantics_new.json

../labutopia-env/bin/python -m demos.lab_cuvette_demo02.data_check \
  --episode outputs/lab_cuvette_loading/V0_demo01/random3_20261019/seed_7000/trial_00/dataset/episode_0000.h5 \
  --score /tmp/seed7000_semantics_new.json \
  --output /tmp/demo02_historical_rejection_new

# 新场景尚无合格 episode 时，明确记录空索引及现有加载器的拒绝。
../labutopia-env/bin/python -m demos.lab_cuvette_demo02.data_check \
  --output /tmp/demo02_no_episode_new
```

真实新轨迹满足几何关口后，可用 `analyze EPISODE --contract scene_contract.json --output NEW_SCORE` 生成新评分，再用 `data_check --episode H5 --score NEW_SCORE --output NEW_INDEX` 运行现有加载器读取一个 batch。当前空索引的拒绝核查不能代替该项成功验收。

## 当前未执行项

正确完整架到正确内部座的新连续物理轨迹、新任务真实成功样例、成功样例的训练 batch、标准五次和合法随机十次均未执行。需要先通过本轮来源架、内部座身份和全深度几何审核；具体场景关口以本轮主报告为准。
