# Project_v1_1 评分、动作回执与数据资格契约审查

本文件限定接口和数据分类，不改变物体、座孔、质量、摩擦、接触参数或原有任务成功阈值。旧 Project_v1 的结果及 H5 不重写。源码审查起点为 `f94f9451ea10022b2e747dae92e419b636f1f695`；本轮新版本的实际运行来源由各集运行清单、场景指纹和最终交付清单确定，本文不预填未来提交。

## 1. 旧接口中需要拆开的含义

旧 facade `demos/lab_cuvette_project_v1/environment.py` 在动作循环退出后设置 `completed=true`；这不能证明目标到达，也不能单独证明请求区间全部执行。其计数原来在 `task.step` 正常返回后加一，无法表示一次调用中物理已经推进、随后记录或渲染失败的情形。

旧 `SizeScorer.update` 将机器人触碰禁止区域和物体输入几何侵入均标为 `PHYSICS_INVALID`。底层 scorer 的非物理失败分支随后把 `task_success` 置为 null，collector 再将其排除出正常训练。这把“连贯仿真中发生的安全碰撞”和“仿真状态失真”合并了。新版仍须立即停机，但不能仅凭有限值碰撞宣称仿真损坏，更不能由碰撞本身推断是策略、执行器或模拟器的责任。

底层 scorer 的任务事件和验收窗口可继续复用：实际抓持、源槽离开、搬运、目标支撑、双指释放、撤离和撤离后稳定窗口，仍由实测物理状态判定。末端终止窗口稳定不等于完成释放、撤离和装载。撤离后窗口不存在时继续输出 unavailable / null。

旧 streaming H5 已保留 before/after 时间、相邻观测、原始命令、实际关节命令、双 RGB、标定和独立评分。新版无需复制整套 writer，也不应改变已被正常 ACT/DP reader 使用的 8D 动作及图像表示。`complete=true` 只表示记录已 finalize，不能代替任务成功、物理可信度或训练资格。

## 2. 每个动作的独立回执

`accepted` 只表示动作通过当前观测身份、数值边界及路径预检；它不表示发生运动。`execution_finished` 表示此次动作的执行生命周期已经闭合，包括完整消费区间、拒绝和部分执行后停止；`completed` 仅为此含义的兼容别名。是否完整消费请求区间必须结合实际控制 tick、实际物理 tick、实际耗时和 `partial_execution` 判断。`target_reached` 独立表示实际 TCP 终点达到声明的位置与姿态容差，不表示抓住物体或完成夹爪开口。`safety_stopped` 应解释为安全守卫触发的停止；普通任务完成、超时或抓持滑落的终止原因另存为任务类别。

应保留如下独立字段：

- 身份与幂等：episode、输入 observation、action ID、payload SHA、执行状态及输出 observation ID；同一 ID 与同一 payload 返回原回执，不再次推进。相同 ID 不同 payload 拒绝。
- 时间与计数：原始请求时长、量化后时长、模拟 before/after 时间、实际 elapsed、完整 control tick 数、实际 physics tick 数、部分控制区间标志。实际时间首选 after−before，不以请求时长或完整 tick 数覆盖半个控制区间。
- 目标：请求开始 TCP、固定最终目标、逐时参考、实际终点。相对动作只在动作开始时解析一次；不能逐 tick 将 delta 重新累加。
- 误差：最终位置误差、最终旋转测地角、最大时序跟踪位置和姿态误差、误差采样覆盖范围。跟踪误差比较同一时刻的插值参考，不能在区间开始即比较最终目标。
- 停止：原始 stop reason、失败域、异常类型、是否部分执行、是否已终止环境。拒绝与执行异常使用不同状态。

纯拒绝应为 accepted=false、0 tick、0 elapsed、无物理推进、原 observation ID 仍有效；保留该 ID 的拒绝回执，换 payload 必须换 action ID。部分执行后不得把操作当作零执行而自动重放；即使抛出异常，也应先查回执。

完整请求区间已消费但 TCP 超出容差，应为 execution_finished=true、target_reached=false。新的自由空间诊断终点门限为 1 mm / 0.5°；约 0.1 mm 的细运动应报告实测误差，不能宣称修改了原装载任务的成功阈值。新环境还记录连续 IK 路径预检及 FK 误差；连续运动学通过不等于碰撞或动力学已认证。

## 3. 物理推进与缓存观测的边界

新 facade 已改为从 task 的 before/after `control_steps`、`steps`、`t` 取差值，因此正常返回之后抛错与半个控制区间抛错都可保留实际推进证据。预检拒绝也保留原 successor observation ID 和零时长，已有 CPU fixture 覆盖。

底层 `get_observation()` 返回 `_obs` 缓存；底层 `step` 在完成物理、渲染之后才更新缓存和 `control_steps`。新版已针对这个边界补充 `exception_state_snapshot`：异常后从实际机器人关节读取 FK 终点，读取失败则 endpoint 无效；无论是否可读 FK，都不把旧 RGB 缓存冒充同步 successor，设置 `successor_observation_available=false`、输出 observation ID 为 null。此时不得继续用旧观测执行动作，环境已进入终止处理。

最大跟踪误差明确声明为“完整 control 边界采样，不是 physics substep 最大值”。异常路径设置 `tracking_error_coverage_complete=false`；已有采样最大值保留，但不宣称覆盖未正常返回的区间。实测非有限状态和无效 quaternion 的解析也必须受异常保护，以 null / validity 字段闭合回执，不能让严格 JSON 序列化错误掩盖原始 cause。

新版已新增 `stop_domain`，`safety_stopped` 只对应 safety / executor / simulation，普通任务失败不再单凭“已终止”置真。纯路径预检拒绝应保持 stop_domain=none 和 safety_stopped=false，含 joint 预检分支；不能因 `JOINT_` 前缀把未执行拒绝误判为执行安全停止。公开回执应保留这些 validity、coverage、scope 和请求/应用夹爪字段，不能仅在本地日志中增加。

## 4. 夹爪三个状态不能互换

工具侧保留上次显式逻辑 opening / effort 请求。环境侧另有受已有接触 latch 影响的 applied opening target；传感器侧还有实际手指位置和接触力。这三个数值各有用途，不能互相覆盖。

move / wait 沿用上次请求；显式 gripper 才改变逻辑开口与每指 effort 上限。新 facade 在逻辑请求未改变时保持实际 applied target，不把接触变形后的实测开口当作新的闭合命令，也不在运动时无意恢复 8 N。预检拒绝之后工具必须恢复原逻辑 opening / effort，不能承认未执行的开口变更。每指上限仍为 8 N；记录的驱动上限不是实测接触力，不按 teacher 阶段或物体真值自动调力。

夹爪受阻时 TCP 到达不代表 opening 到达或稳定抓持。应结合实际双指开口、双侧接触和图像判断，保留 applied target 与 raw request，避免将同一逻辑命令的 latch 限制误记为模型改变指令。

## 5. 评分的相互独立轴

`task_result` 保存三态 success（true / false / null）、status、scope 和 failure_domain。完整装载与诊断子任务使用不同 scope。无法评价任务结果时保留 null，不能为了凑失败数改成 false。

`record_integrity_valid` 由 collector 对动作、传感器、相邻时间、有限值、索引和独立评分证据核对。scorer 结束时一般为 null / collector_pending；已知物理记录时钟不一致可先判 false。`physics_trustworthy` 表示记录的物理状态在声明范围内是否可信，取 true / false / null；它不认证原生速度、有效 cooked collision geometry 或真实世界标定。数据写完整不等于物理可信；物理状态连贯也不保证采集完整。

`success_bc_eligible` 只允许完整 loading、独立任务成功、物理可信、记录完整、几何声明合格的轨迹。正常 loader 兼容字段 `eligible_for_success_bc` 同步保守投影。`trajectory_analysis_eligible` 允许记录完整且存在 transition 的诊断轨迹，即使任务未知或物理不可信；它仅表示可分析记录，不允许自动进入成功训练。

`record_valid` 保留旧 loader 可理解的保守投影：记录完整、物理可信、属于可评价任务的类别。它不再承担解释全部原因的工作。成功 BC、有效任务失败分析和诊断轨迹分析分别筛选，不以一个 valid 字段互相替代。

## 6. 停止类别及责任归因

- 任务：GRASP_SLIP、DROPPED、BLOCKED、UNSTABLE_AFTER_RELEASE、TASK_INCOMPLETE 等；可评价的完整任务失败为 false。
- 安全：有限、连贯状态中的禁止 robot/environment 接触为 SAFETY_COLLISION；已有同阈值输入几何侵入守卫为 SAFETY_GEOMETRY_VIOLATION。继续立即停止。合格物理中的完整任务为 false，而不是自动 PHYSICS_INVALID / null。正常任务允许的物体接触不进入此类。
- 执行器：CONTROL_OR_IK_FAILURE、TRACKING_ERROR、已知连续性/关节/实际速度执行守卫和执行回执异常为 EXECUTOR_FAILURE。保存实际运动与已执行 tick；本轮任务结果为 unknown，不能笼统称 simulator failure。
- 仿真：实测非有限状态或超过既有阈值的实际物体 pose jump 才进入 SIMULATION_FAILURE，physics_trustworthy=false、任务 unknown。单独一个旧 PHYSICS_INVALID 标签没有足够细证据时应为 unclassified，而非推断根因。
- 记录：非单调记录时钟或采集链损坏为 RECORDING_FAILURE / 记录资格失败；不能直接将根因归到模拟器。
- 服务与协议：供应商调用失败为 service；格式、身份、上下文和协议拒绝为 protocol。预算、墙钟预算和进程中断单列，不算任务成功，也不混成碰撞或求解器故障。

并发事件必须保留原始 chronology。执行偏差后碰撞可以同时具有执行器事件与安全后果；仅有碰撞不能判策略责任。新版保存 `raw_failure_type`、`raw_termination_reason`、`legacy_invalid_state_reasons`、`legacy_guard_events`、`base_scoring_diagnostics` 和 `safety_event`，`safety_attribution` 明确为 scorer 未判定责任。首次实际守卫及原始事件证据不删除。

## 7. 最小接入实现

`demos.lab_cuvette_project_v1_1.scorer.Scorer` 继承 SizeScorer；保持 `update(row)` / `finalize(episode_id, task_type, termination_reason=None, failure_type=None)` 签名。每行先运行原事件及窗口逻辑，再派生新的分类。旧安全原因仅从新版实例的“数值损坏原因集合”移出，同时完整保留旧诊断。原控制、几何和成功门限不变。

`data_collectors.lab_cuvette_project_v1_1_collector.LabCuvetteProjectV11Collector` 继承原 streaming collector；接口仍为 `begin_episode(...)`、`cache_transition(...)`、`finish_episode(result, independent_score=None)`。首次 finalize 先由原 writer flush / close，再仅对该实例刚创建的 H5 以 r+ 追加新资格 attrs、`qualification_json` 和 `task_result_json`；保留原 `independent_score_json`，并同步本集 result / meta 的 labels。重复 finalize 拒绝，历史 H5 不开放此路径。待资格补全前 attrs 为 unknown / false，正常 reader 保守拒绝，避免后处理失败被当成合格记录。

scorer 的完整独立结果仍应在 task 的 `independent_score.json` 中保存；collector 返回字段不得覆盖它的 schema。新增顶层字段为 `qualification_schema`。资格文档使用 `labsim.Project_v1_1.qualifications.v1`；独立评分为 `labsim.Project_v1_1.independent.v1`。

`policy.dataset.lab_cuvette_project_v1_1_dataset.LabCuvetteProjectV11Dataset` 继承正常 MinimalPickDataset，维持 ACT / DP 的绝对 8D 动作和 RGB 表示。除正常父类样本过滤外，强制 Project_v1_1、standard、完整 loading、允许的 condition_group、新资格 schema、单一 64 位 scene fingerprint、记录完整与物理可信。默认 success 还强制 success_bc_eligible=true。失败样本仅可显式使用 failure / all_valid；执行器、服务、仿真及诊断子任务不能作为正常完整任务训练数据。

新版 H5 不混入旧 Project_v1 reader，旧记录也不自动进入新版 reader。历史重分析若需要，另写分析 sidecar，包含 source H5 SHA、旧 scorer 版本和新派生版本；不改旧 attrs、独立评分、success、record_valid 或历史统计。不能将分析资格提升成训练资格。

## 8. 已执行 CPU 验证与未宣称内容

本轮新增 scorer 的 14 项合成 fixture 检查通过：沿用相同成功谓词、有限碰撞分类、同阈值几何守卫、控制 / 跟踪失败、非有限 / pose jump、混合事件、记录时钟、服务、预算、空记录及原有观测限制。数据的 8 项 CPU 检查通过：成功与安全失败正常读取、ACT / DP 动作和 RGB 形状、H5 hardlink 与原独立评分保留、记录失败与物理失败轴分离、诊断排除、旧 reader 隔离、重复 finalize 防改写。

运行命令：

```bash
/tmp/labsim-handoff-ci-py311-20261022/bin/python -m pytest -q tests/test_lab_cuvette_project_v1_1_scorer.py
CUDA_VISIBLE_DEVICES='' PYTHONPATH=. /home/wujing/Desktop/vla/labutopia-env/bin/python -m unittest discover -s tests -p test_lab_cuvette_project_v1_1_data.py -v
```

这些是 CPU 合约测试，不证明真实抓持、搬运、装载或控制精度。本文作者未启动 Isaac、GPU、API 或训练。真实新版本物理复现、动作误差、相机输入和预算结果以独立运行证据为准。原生速度、有效 cooked geometry 和真实标定未核查边界继续保留。
