# 器皿装载 Progress v1.2

Progress v1.2 为当前 `lab_cuvette_loading / Project_release_v1 / standard` 提供因果阶段注释、有效连续进展、抓持尝试、漂移分区统计和便携视频报告。每个物理步计算、每个控制 transition 记录；环境动作、reward、独立 scorer 和数据资格沿用发布版。

## 运行完整任务

先按[组内使用指南](../../development/ONBOARDING.md)准备 Isaac Python 与固定资产缓存。正常 Teacher 完整装载入口：

```bash
./labsim demo --project-version Project_release_v1 --backend teacher --gui \
  --record-mode collect --record-purpose demonstration --progress \
  --output outputs/lab_cuvette_loading/Progress_v1_2/teacher_001
```

`collect`、`eval`、`serve` 的发布版入口同样接受 `--progress`。省略该开关，保持原始任务行为。场景采用 standard，资产 revision 继续使用工程锁定值；不开 random。

## 分析已有记录

等待仿真进程退出、H5 完整发布后分析。输出使用原 episode 之外的新目录，原记录保持只读：

```bash
./labsim progress episode /absolute/path/to/episode_0000 \
  --output outputs/lab_cuvette_loading/Progress_v1_2/offline_001

./labsim progress index /absolute/path/to/demonstrations.hdf5 \
  --output outputs/lab_cuvette_loading/Progress_v1_2/index_001

./labsim progress compare /absolute/path/to/online/episode_0000 \
  outputs/lab_cuvette_loading/Progress_v1_2/offline_001 \
  --output outputs/lab_cuvette_loading/Progress_v1_2/consistency_001.json

./labsim progress report outputs/lab_cuvette_loading/Progress_v1_2/offline_001 \
  --episode /absolute/path/to/episode_0000 --copy-videos
```

优先读取原 `physics_records.jsonl.gz`，逐个实际物理步处理。H5-only 模式明确标为控制端点采样，端点之间的瞬变没有高频证据。原始 PhysX 回调冲量仅作接触来源审计，不重复叠加到已有力张量。

浏览器不支持原 MP4v 视频时，复用便携工具生成 H264 显示副本；该过程保留原帧、帧率、时长、时间戳和来源哈希：

```bash
"$LABSIM_PYTHON" docs/lab_cuvette_loading/Progress_v1_2/tools/portable_report.py \
  --progress outputs/lab_cuvette_loading/Progress_v1_2/offline_001 \
  --episode /absolute/path/to/episode_0000 \
  --output outputs/lab_cuvette_loading/Progress_v1_2/portable_001
```

## 阅读输出

先打开 `progress_report.html`，按阶段跳转到对准、插入、交接、释放和撤离区间。光标同时显示请求时间与实际控制样本时间；数值取真实端点，不插值伪造采样。局部图保留亚毫米波动，位置、角度、力、时间和归一化量分图显示。

- `progress_v1.jsonl.gz`：文件名兼容既有工具，内容 schema 已显式升级；包含全部控制步的 before、after 及区间事件。
- `progress_events.jsonl`：追加式候选、确认、条件变化、操作结束和结果更新事件。
- `progress_summary.json`：最终阶段、尝试、漂移区间统计、来源身份、原结果与开销。
- `progress_config.resolved.json`：几何、阈值、归一化尺度、来源、版本与指纹。

原任务最终结果、Progress 历史覆盖率、当前有效进展和原始几何量分别展示。已完成阶段的正常物理后继不会显示为抓取或搬运失败。原始 `current_satisfied` 仍忠实记录当前条件，包括正常退出时的 false。

## 关键接口

有效插入需要正确目标、入口区域、姿态和同次合法操作链路。已知错误区域或前置条件不满足时，有效值为 0 并给出原因；必要证据未知时为 null。合法承托及释放后的入座证据延续同一尝试。原始投影可以超出目标深度，保留用于诊断。

接近质量按 `1/(1+error/scale)` 分别输出位置与姿态质量，尺度是独立配置的诊断尺度。离散接近阈值与最终成功条件不变，Progress 不写入 reward。

抓持参考在同一尝试中固定，统计区间按物理事件划分，不按 grasp_quality 筛选。操作结束与结果确认分开：合法释放先结束操作区间，稳定验证之后追加同一 attempt 的 outcome 更新。事件重放可恢复尝试及重试关系。

版本与旧字段对应见[迁移说明](migration.md)，本轮实际结果、验证与局限见[RESULTS](RESULTS.md)。上一版文档及输出保留在 [Progress v1 历史目录](../Progress_v1/README.md)。
