# Progress v1.2 迁移与字段语义

本文对应 `lab_cuvette_loading / Project_release_v1 / standard`。运行、离线分析与报告入口见[当前指南](README.md)，完整机器可读字段见 [schema](schema.json)。原始资产、物理配置、控制器、reward、独立 scorer 和数据资格规则保持发布版基线。

## 版本与保存约定

上一版参数文件已经使用 `Progress_v1.1`。本版采用独立标识：

- 物理计算快照：`progress_schema_version = labsim.Progress_v1_2.v1`。
- evaluator：`progress_evaluator_version = Progress_v1_2.causal_physics.v1`。
- 参数文件：`config/lab_cuvette_loading/Progress_v1_2/progress.json`，`schema = labsim.Progress_v1_2.parameters.v1`、`version = Progress_v1.2`。
- 控制步、事件及 summary 文件包装层：`schema = labsim.lab_cuvette_loading.progress.v1.2`。summary 中 `progress_schema_version` 是这一包装层标识，`evaluator_schema_version` 保存计算快照 schema。
- HTML：`report_version = Progress_v1.2.portable.v1`。

Python 导入路径 `demos.lab_cuvette_progress_v1` 和文件名 `progress_v1.jsonl.gz` 保留，以复用原入口。应读取上述版本字段判断语义，不能按包名或文件名推断版本。

历史 H5、原视频、原判分和旧 Progress sidecar 保持原样。重算使用 episode 之外的新目录。旧的 resolved Progress 配置保留为来源证据，不直接传给 v1.2 evaluator：遇到其他 `progress_schema_version` 会明确拒绝。请提供原始任务 YAML 与 episode 元信息，由新版 `resolve_config()` 重新解析，生成新 resolved 配置及指纹。

## 原始量与有效进度

`metrics` 中每项均带 `available`、`value`、`unit`、`source` 和缺失时的 `reason`。读取器必须保留 `null`，不能统一补成 0。

### 插入字段

- `raw_axial_depth_m`：新增原始轴向投影，单位 m；优先保留原 `PhysicsRecorder.capture.depth_m`，证据允许时使用声明的几何投影后备。保留入口外负值及超出目标深度的值。顶层及 `metrics` 均提供该字段。
- `raw_depth_fraction`：新增未截断比例，等于 `raw_axial_depth_m / target_depth_m`。可以小于 0 或大于 1，不表示有效完成度。
- `metrics.raw_depth_m`、`metrics.depth_ratio`：保留旧诊断接口。`depth_ratio` 仍是旧的截断深度比例。
- `stages.insert.continuous`：保留旧截断原始深度比例语义。v1.2 仍可能在来源架得到 1；消费者必须将它作为旧诊断量读取。
- `valid_insertion_progress`：新增有效插入进度，顶层及 `metrics` 均提供；已知适用时为截断后的 0–1 比例，已知不适用时为 0，必要证据无法判定时为 `null`。
- `insertion_progress_applicable`：`true / false / null`，分别表示适用、已知不适用和证据未知。
- `insertion_gate_details.gates`：逐项记录 `correct_target`、`entrance_region`、`orientation`、`current_attempt_route`、`held_or_transferred` 的 `value / source / reason`。
- `insertion_gate_details.not_applicable_reasons` 与 `unknown_reasons`：分别列出已证实的排除原因与缺失证据。存在已知排除项即可确定不适用；没有已知排除、但必要证据缺失时保持 unknown。

有效插入依据当时的正确目标、入口区域、实际姿态和同次操作链路。合法目标承托后允许保持链路，不要求释放后的夹爪继续持物。最终 `task_success` 不参与过去快照的计算。

### 每阶段连续量

`stages[name].continuous` 保留旧原始诊断语义；新增 `effective_continuous` 表示有任务门控的连续量，`continuous_semantics` 明确两者区别。

v1.2 的 `current_stage_continuous` 使用当前阶段的 `effective_continuous`，并附带 `current_stage_continuous_semantics`。这是显式版本化的语义迁移；需要重现旧读数时，读取 `stages[current_stage].continuous` 或保留的旧输出。

有效离架量要求实际持物；有效搬运量还要求同次离架链路；有效对准量要求合法路线与持物或已完成的承托交接；有效支撑量要求正确目标、深度、姿态、间隙和已观察重叠检查。几何距离或某一接触力单独出现，不等同于这些阶段已完成。

### 接近质量

新增 `metrics.approach_position_quality` 和 `metrics.approach_orientation_quality`，分别采用：

```text
position_quality = 1 / (1 + position_error_m / approach_distance_scale_m)
orientation_quality = 1 / (1 + abs(orientation_error_rad) / approach_rotation_scale_rad)
```

默认独立诊断尺度为 0.1 m 和 π/6 rad，来源记录在 resolved 配置的 `sources`。接近阶段 `effective_continuous` 是两项质量的几何平均；缺少任何必要分项时保持 `null`。原始位置、姿态误差仍在 `grasp_approach_position_error_m` 与 `grasp_approach_orientation_error_rad` 中。

旧 `stages.approach_grasp.continuous` 的截断线性量保留。完成阈值使用原有离散接近条件；归一化尺度并非位置精度、成功门槛或新增 reward。

## 当前物理条件、历史里程碑与用户状态

`current_satisfied` 和 `stage_vector` 继续记录当前三值物理条件。`ever_achieved` 与 `highest_ever_stage` 记录历史达成，不阻止当前回退。`coverage_progress` 是九阶段等权历史覆盖率，不是当前有效插入比例，也不是原任务成功率。

旧 `status` 保留兼容。界面应优先使用新增的 `user_status` 与 `user_status_reason`：

- `active`：当前正在执行，或相应物理条件当前满足。
- `completed_followed`：该阶段已达成，并有合法物理后继证据解释当前条件退出。
- `temporarily_unmet`：历史达成，但当前条件失效，尚无足够的合法后继解释。
- `evidenced_failure`：当次尝试存在独立观察到的失败或异常事实。
- `evidence_missing`：当前必要物理证据不足。
- `not_started`：尚无该阶段候选或当前执行要求。

因此，合法释放后抓持条件为 false，仍可显示 `completed_followed`；进入有效插入后离开预插入位置，也可作为合法搬运后继。状态解释使用实际几何、接触及同次尝试链路，不读取 Teacher 的 `phase` 作为成功证据。

原 `hold_state = unsupported_or_lost` 保留。界面改读 `hold_state_user`：无丢失证据时为 `support_unconfirmed`（承托未确认），存在当前尝试的实际抓持丢失事实时为 `unsupported_with_observed_loss`。`actual_grasp_loss_observed` 单独记录后者。承托暂未确认不能直接标为掉落。

## 抓持漂移：三个明确区间

同一 attempt 在首次有效双指保持后只建立一次 `relative_pose_reference`，包含参考时间、器皿在实际手掌坐标系中的位置及 wxyz 四元数。新尝试建立新参考；当前尝试不因质量变差或承托交接而重置参考。

`attempt.relative_motion_statistics` 包含：

1. `operation`：`reference_t <= sample_t <= operation_end_t`，覆盖整个操作区间，包括支撑交接。
2. `before_first_target_support`：从参考建立到首次 `support_transfer` 确认之前，右端开区间。若未发生目标支撑，统计至操作结束。
3. `support_transfer`：首次 `support_transfer` 确认至操作结束，包含边界。未发生首次支撑时保持 unavailable，不从 episode 结束时间虚构区间。

每区间记录 `declared_start_t / declared_end_t / end_inclusive`、实际 `sample_start_t / sample_end_t`、参考位姿与时间、标称及观察采样频率、有效/缺失样本数，以及平移和旋转峰值、峰值时间、承托状态和对应抓持质量。

计数说明：

- `valid_sample_count` 要求该观察行的平移和旋转均有效；另有每分量的有效及缺失计数。
- `missing_sample_count` 统计已观察行中的缺失证据，不会为采样缺口补造行数。
- `grasp_quality_false_sample_count` 与 unknown 计数保留；`quality_filter_applied = false`，质量不合格的真实相对运动仍参与峰值。
- 优先使用原物理记录，标准基线为 240 Hz。报告光标使用 60 Hz 控制端点，二者最大值可能不同，不能混成同一采样口径。

v1.2 的 attempt 顶层 `maximum_relative_translation_m / maximum_relative_rotation_rad` 明确对应整个 `operation` 区间。旧版曾在 `_loaded_pose_seen` 后停止累计，既不是整个操作区间，也不能直接当作新的“首次目标支撑之前”区间。跨版本比较请使用命名区间及其边界，不比较同名数字后推断控制变差。

交接期间器皿相对手掌发生合法运动，不自动等于抓持失败。失败仍依据独立物理失败证据；漂移统计用于完整呈现相对运动。

独立复算入口直接读取原始物理记录与声明区间，并检查 summary：

```bash
"$LABSIM_PYTHON" docs/lab_cuvette_loading/Progress_v1_2/tools/audit_attempts.py \
  /absolute/path/to/episode_0000 /absolute/path/to/new_progress_directory \
  --output /absolute/path/to/new_attempt_audit.json
```

## 首次确认与阶段耗时

全局 `milestones`、阶段快照和当次尝试的 `stage_timing` 区分：

- `first_candidate_t`：首次候选成立的时间，不因候选失效重置。
- `first_confirmed_t`：首次满足保持时长等条件的确认时间。
- `last_confirmed_t`：最近一次从未满足状态重新确认的时间，不是最后一条 true 样本时间。
- `confirmation_count`：确认事件数量，不是满足条件的物理采样行数。

旧 `attempt.completed_stages[name]` 曾被重新确认覆盖。v1.2 将其固定为首次确认时间；需要原“最后确认”语义的消费者改用 `attempt.stage_timing[name].last_confirmed_t`。

`stage_timing.duration_basis` 声明为“首次候选至首次确认”；同时提供 `first_candidate_to_first_confirmation_s` 和 `attempt_start_to_first_confirmation_s`。阶段若在 attempt 开始前已达成，使用全局 milestone，不凭空给当次尝试补写一条更早事件。界面分列首次候选、首次确认、最后确认和确认次数，不用最后重确认时间计算首次完成耗时。

## 尝试事件与最终结果闭环

操作区间和最终结果分开：

1. `attempt_started`：建立 attempt 身份、前后尝试及恢复关系。
2. `attempt_ended`：结束操作区间，记录 `end_t / operation_end_t / operation_end_reason`。合法目标释放的 `outcome_status = awaiting_stability`、`outcome = incomplete`，表示等待后续稳定验证。
3. `attempt_outcome_updated`：关联同一 `attempt_id` 追加结果变化；稳定确认后变为 `success`，记录 `outcome_confirmed_t`、`outcome_reason` 与 `final_outcome_confirmed`。不改写旧事件或已返回的控制快照。

稳定窗口中断会追加 `stable_window_interrupted`，并为关联尝试追加临时 incomplete 更新，保留 `awaiting_stability`。观察恢复后可以通过新的连续稳定窗口确认成功。结束前尚未完成稳定验证时，finalize 根据实际终止域记录 incomplete 或 interrupted；超时与服务中断分域保留。重复 finalize 返回同一结果，不重复发出结果更新。

每个生命周期事件带独立 attempt receipt；确认/候选事件也保留关联 ID。`replay_attempts()` 只读取追加式事件即可恢复尝试数、重试关系、操作结束原因和最终 outcome；`verify_replay()` 再与 summary 对照。原始条件切换不删减，也不把每次重新确认当作新尝试或可重复成功奖励。

```bash
./labsim progress replay /absolute/path/to/new_progress_directory \
  --output /absolute/path/to/new_event_replay.json
```

`summary.event_statistics` 分开记录原始条件切换数量、操作尝试数量、重试数、首次阶段达成数和重复确认数。HTML 提供归并视图，同时保留完整原始事件入口。

## 可视化、采样时刻与视频移交

HTML 只嵌入绘图和光标必要的标量、状态及事件摘要，不嵌入完整 before/after、图像或场景对象。完整 sidecar 保留在相邻文件。

- 光标同时显示请求仿真时间、实际控制样本时间、两者时间差及关联视频帧仿真时间。取请求时间之前最近的原始控制端点，不插值，也不从抽稀曲线读取数值。
- 全程曲线允许保留极值及边界后抽稀；局部区间绘制原始控制端点，极值计算始终使用全部原始控制行。unknown 为断段，首次确认和稳定窗口中断独立标记。
- 位置/净距为 mm、姿态为 °、力为 N、时长为 s、有效进度为 0–1，分图显示。轴向原始深度和未截断比例保留真实取值。
- 阶段按钮分别跳转对准、插入、支撑交接、实际释放、实际撤离和稳定完成；“对准—撤离局部”、光标附近及手动起止时间支持亚毫米操作观察。阈值线来自 resolved 配置，不能解释为接触精度。
- 原任务最终结果、Progress 历史覆盖、当前有效进度与原始几何量在不同位置标明。最终结果可在页面全程显示；过去的因果快照仍保持原值。

视频采用真实录制文件，关联原 `video_timestamps.json`。MP4 的显示时间由实际录制帧索引和帧率确定，与该帧的仿真时间分别记录。H264 便携副本由已有工具保留原帧数、帧率和时长，并附原文件与副本 SHA256。

便携目录可直接在支持对应编码的浏览器中打开本地 HTML。若通过 HTTP 查看，服务器需要支持视频 byte-range 请求，才能可靠定位；普通 Python `http.server` 在本轮浏览器检查中可加载画面，但未提供可用的 seek 区间。视频存在却不能跳转时，先检查编码和服务器的 Range 支持，不修改仿真时间映射。报告无 CDN 依赖。

## 数据使用迁移

原 `task_success / record_valid / success_bc_eligible`、H5 标签和数据用途筛选继续作为原任务数据资格入口。新增 Progress 是旁路注释，不直接改变训练标签或 reward。

新消费者推荐读取：

```python
stage = snapshot['current_stage']
effective = snapshot['stages'][stage]['effective_continuous']
valid_insert = snapshot['valid_insertion_progress']
applicable = snapshot['insertion_progress_applicable']
raw_depth = snapshot['raw_axial_depth_m']
status = snapshot['stages'][stage]['user_status']
```

不要用 `insert.continuous == 1`、历史覆盖率或几何预插入完成来筛选完整装载成功。需要原版本行为时读取旧输出或相应固定提交；需要 v1.2 时在新目录重算，并将 evaluator、参数、原 episode 身份和代码提交一起记录。
