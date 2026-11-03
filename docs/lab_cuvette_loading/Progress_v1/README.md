# 器皿装载 Progress v1

Progress 在每个控制 transition 给出当前物理阶段、连续指标、历史里程碑、抓持尝试和未完成要求。适用任务为 `lab_cuvette_loading / Project_release_v1 / standard`。在线和离线共用 `ProgressEvaluator`，不会推进仿真，也不改变动作、reward、独立评分或数据资格。

## 开启正常任务的在线记录

先按[组内使用指南](../../development/ONBOARDING.md)准备 Isaac Python 和固定资产缓存，再运行：

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration --progress \
  --output outputs/lab_cuvette_loading/Progress_v1/teacher_001
```

`collect`、`eval`、`serve` 的同一版本也接受 `--progress`。省略开关保持原行为。用途与 Progress 无关：正常 Teacher 示范使用 `demonstration`，策略评测使用 `policy_evaluation`，接口试验显式使用诊断用途。

Progress 在 reset 第 0 步开始计算，包含器皿初始自然落稳。每个物理步更新因果条件，控制步保存动作前后指标和区间事件。原任务发布记录前，Progress 先关闭 sidecar；旁路写入失败会留下 `partial` 或 `interrupted` 状态，原任务结果继续由原评分与采集器决定。

## 对已有记录离线分析

等待源仿真进程退出、H5 完整发布后执行。输出必须为新目录，且位于原 episode 之外：

```bash
./labsim progress episode /absolute/path/to/episode_0000 \
  --output outputs/lab_cuvette_loading/Progress_v1/offline_001

./labsim progress index /absolute/path/to/demonstrations.hdf5 \
  --output outputs/lab_cuvette_loading/Progress_v1/index_001

./labsim progress report outputs/lab_cuvette_loading/Progress_v1/offline_001 \
  --episode /absolute/path/to/episode_0000 --copy-videos

./labsim progress compare /absolute/path/to/online/episode_0000 \
  outputs/lab_cuvette_loading/Progress_v1/offline_001 \
  --output outputs/lab_cuvette_loading/Progress_v1/consistency_001.json
```

单集也接受根 H5 路径。默认读取 episode 的 `config.yaml`；自包含 H5 没有配置时，传 `--config` 指定实际配置。批处理支持 ExternalLink、copy 和历史根分组索引，并保留成员排除原因。索引用途选择沿用[既有数据入口](../Project_release_v1/data_usage.md)。

优先使用 `physics_records.jsonl.gz` 的高频实际状态；原生接触回调日志用于来源与重复事件审计，冲量不重复加到力张量。只有 H5 控制频率端点时，输出明确降为 `control_frequency_only`：持续时间按已观测端点累计，确认时间是首次满足条件的控制采样点，不能证明端点之间没有接触或姿态瞬变。缺失字段输出 `available=false` 和原因。

## 输出与阅读顺序

- `progress_summary.json`：终局分析、尝试、历史里程碑、输入来源、原结果、完整性、体积及开销。
- `progress_v1.jsonl.gz`：每个控制 transition 的 `before`、`after`、当前阶段向量、连续指标及区间事件。
- `progress_events.jsonl`：候选、确认、物理条件丢失、重试和稳定窗口中断等稀疏事件。
- `progress_config.resolved.json`：独立版本化的几何、阈值、归一化尺度、来源与哈希。
- `progress_report.html`：阶段时间线、误差/深度/滑移/支撑/净距/稳定曲线和真实视频时间关联。`--copy-videos` 复制原始侧视和腕视，方便移交。

`progress_input_metadata.json` 是在线运行的固定几何及初态绑定；离线回放复用这些输入。原 H5、图像和物理日志不复制进逐步 Progress，也不修改历史标签。完整副本的哈希在源关闭后的离线核查中记录；在线闭合发生在 H5 最终发布之前，H5 哈希状态会明确说明。

控制记录和 sidecar summary 的 `schema` 为 `labsim.lab_cuvette_loading.progress.v1`；其中 `before`、`after` 等核心快照的 `progress_schema_version` 为 `labsim.Progress_v1.v1`。summary 的 `evaluator_schema_version` 标出核心版本。`config_hash` 对不含自身的解析配置求哈希，`config_sha256` 对包含该字段的完整配置求哈希，二者用途不同。

原录制视频采用 MP4v 时，部分浏览器无法内嵌播放。可用已有 FFmpeg 生成带来源哈希的 H264 显示副本；保留全部原帧及时间，不改原录像：

```bash
"$LABSIM_PYTHON" docs/lab_cuvette_loading/Progress_v1/tools/portable_report.py \
  --progress outputs/lab_cuvette_loading/Progress_v1/offline_001 \
  --episode /absolute/path/to/episode_0000 \
  --output outputs/lab_cuvette_loading/Progress_v1/portable_001
```

直接打开便携目录内的 HTML；通过静态服务器查看时，服务器须支持 HTTP Range 才能按时间拖动视频。`portable_media_receipt.json` 保存原录像及显示副本的哈希、帧数、时长和转换命令。

## 指标与阶段

详细定义见[字段映射](field_mapping.md)、[阶段判据](stage_criteria.md)和 [schema](schema.json)。内部长度单位 m、时间 s、角度 rad、力 N。

当前状态允许回退；`ever_achieved` 和 `first_confirmed_t` 保留历史事实。候选开始时间与确认时间分开记录，例如连续稳定 3 秒后才确认完成。`coverage_progress` 是九阶段等权历史覆盖率，不是当前物理成功概率或 reward。

承托状态分别为来源几何支撑候选、夹持、目标承托、失去支撑及未知。目标合法承托后的松爪不会被判成搬运丢失。`release_retreat` 内分别保留实际脱指和整手撤离；撤离使用三个夹爪链接输入几何的保守净距下界，TCP 距离仅作辅助。

原 `task_success`、`record_valid`、物理质量和 BC 资格仍由现有独立 scorer/collector 决定。Progress 的 `termination_domain`、`unfinished_requirement`、`failure_observation` 分别描述结束类型、尚缺要求和实际失败事实。无下降请求、接触和持续窗口证据时，深度停住只记未完成，不直接认定卡滞。

## 几何及证据范围

固定资产为 `cuvette_xy_1000`，10×10×67.5 mm 尺寸假设、20 g 工程质量；完整 6×6 来源架 A1、原内部 A 座 `candidate_far_hinge`。装载参照为原座局部坐标加 `(0.00065, 0.000001, 0) m`，目标深度读取配置为 0.027 m。器皿底部使用实际变换后的包络，不假设 USD 根节点位置。

对准诊断阈值与原 scorer 的 loaded-pose 候选条件逐项映射；它们不构成独立的最终精度声明。当前输入材料几何检查与接触证据不等于完整 PhysX cooked 表面测量。原生速度与位姿差分保留为不同信号，不将差异抹除。

## 开发与验证

核心接口：`reset(metadata)` → `update(actual_physics_sample)` → `finalize(termination)`。每个实例只属于一集；reset 清空尝试、首次事件和持续窗口，重复 finalize 返回相同结果。测试 fixture 与正式示范/策略索引隔离。

```bash
"$LABSIM_PYTHON" -m pytest -q tests/test_lab_cuvette_progress_*.py
```

本轮实际验证记录与运行提交见 [RESULTS](RESULTS.md)。资产发布 revision 沿用现有锁文件；Progress 不发布新资产，也不开展训练或付费策略调用。
