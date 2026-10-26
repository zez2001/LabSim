# 教师 v7 首条完整成功：支撑门与便携读取验收

`teacher_support_align_01` 是代码 `0b922ece8177cb646890bd4d64dedea384991220` 的一条已关闭确定性教师运行。规范退出证明为 PID 845192 已消失、原进程 exit 0。原最终结果为 `task_success=true`、`record_integrity_valid=true`、`physics_trustworthy=true`、`success_bc_eligible=true`，不是 GPT 成功，也不是五条运行结果的提前汇总。

## 原支撑判据实际成立

[逐物理步摘要](summary.json) 对完整 raw 归档流重新计算原 XY 100 µm、倾角 0.15°、偏航 0.2°以及原深度、底部间距、分类座底支撑力 ≥0.1 N 和 inside 判据；解压 SHA256 与字节数均等于归档前原值。

首次 `correct_target_supported` 为 **110.054167 s**：XY 29.829 µm、倾角 0.070935°、偏航 −0.005959°、深度 27.000479 mm、座底间距 −0.479 µm、分类座底支撑力 0.376174 N。它早于 OPEN 阶段 **112.016667 s**。OPEN 同时刻 XY 5.581 µm、倾角 0.012933°、偏航 −0.003618°、底部支撑 0.239238 N，全部原门槛成立；实际两指开空且脱离在 **112.191667 s**，撤离净空事件在 **116.416667 s**。122.666667–125.666667 s 的完整三秒窗口包含 721 个物理样本，稳定=true。

前一条 v6 `teacher_baseline_close_01` 在 OPEN 时已有底部支撑，但 XY 187.961 µm 超过同一 100 µm 门槛，原 `TASK_INCOMPLETE` 保留。本次 v7 实际补齐缺失的独立支撑事件与事件顺序；没有放宽评分。抓持期原杯体相对漂移最大 19.512 µm、配置锚点最大 2.828 µm；三秒末窗位置漂移 0.420 µm、姿态变化 0.015113°。这些是本仿真声明检查范围内的量，不能作为真实精度或平台精度结论。

实际 SUPPORT_TRANSFER 有 264 个控制 tick，其中 80 tick 的教师逻辑卸载时钟暂停。暂停期间通用 helper 仍可追赶既有调度或回闭：26 tick 的 applied 总开口增加，最大 +5.290 µm/tick；8 tick 回闭，最大 −167.229 µm/tick。暂停不等于实测夹爪冻结。该阶段实际有 56 tick 的 release slew、4 tick 的力保持反馈，物理 watchdog 未触发。详见 [控制时序 CSV](support_controller_actual.csv) 与[物理控制边界 CSV](support_release_physics_control_boundaries.csv)。

## 正常 H5 与动作/时间验收

[便携验收 JSON](portable_success_acceptance.json) 引用真实 [normal reader 证明](../../validation/teacher_support_align_01_normal_reader.json)：`LabCuvetteProjectV11Dataset` 的正常 `success` 过滤下，ACT 与 DP 均实际读出一个 batch，`failure` 过滤按真实资格拒绝；没有训练或优化器运行。ACT 动作 batch 为 `[3,16,8]`，DP 动作 batch 为 `[3,16,8]`，双相机图像实际可读且数值有限。

原 H5 包含双相机图像、动作、前后关节状态、语言和 JSON 元数据，没有 ExternalLink、外部 dataset storage 或外部 VDS 数据依赖。以同一只读 H5 的临时替代路径实际读取成功，不复制或重写 H5；这证明文件数据依赖自含和正常 reader 可从替代路径读取，不等于新机器部署或训练验证。原文件约 1.94 GB，不放进精简阅读包。其固定路径、SHA256 与大小均在验收 JSON 中；元数据里的源工程路径保留为出处，不作 HDF5 外部数据链接。

动作接口为 `Project_v1_1.actions.v1`。`actions[8]` 存储七个绝对手臂关节目标（rad）与左指目标（m）；完整执行目标 `control_auxiliary/command_q[9]` 另含右指目标，并已核对两指对称、8D 投影一致。实测前后关节状态独立保存，不能把动作目标当成实际状态。四元数顺序为 wxyz；观测在动作之前，next state 在显式物理子步之后。7539 个转换连续，首观测 0.016667 s、末 next state 125.666667 s，记录区间合计 125.650000 s，前后时间差与区间误差为零，邻接 next/pre 关节状态逐值一致。传感器时间与状态时间仍保留各自原始时钟，不能由此声称像素严格同刻曝光。

[完整闭合读取/归档证明](../teacher_support_align_01_closed_read_archive.json) 已全读 40 个唯一数据集对象；183 个原非 raw 文件 SHA256 全部不变。两份 raw JSONL 从 1,809,908,119 B 无损压至 270,516,738 B，节省 1,539,391,381 B；逐份解压 SHA256 与字节数均相等。原 H5、标签、视频、退出证明未改。原独立评分的 `collector_pending` 快照保留，最终 result/H5 attr 的完整性来源为 `streaming_collector_checks_at_flush_close`；本次离线全 H5 读取是额外的独立证明。

## 完整视频和退出限制

[完整双视角录像](../../media/teacher_support_align_01_full.mp4) 是原视频字节复制，3771 帧、22,196,044 B，覆盖同一次完整运行。其 CPU 全解码、全部 PTS 和支撑/开爪/撤离/三秒窗口关键帧检查见[独立媒体回执](../../media/teacher_support_align_01_full_media_receipt.json)。帧图只是视觉检查，成功依据仍是独立物理与事件记录。VERIFY/终点腕视中的目标局部被左边画幅裁切，侧视目标较小且受机器人/仪器遮挡，不能写撤离后始终完整清晰可见。

本 GUI 进程退出阶段有真实 UI 回调异常：[准确原日志片段](GUI_shutdown_warning_exact_excerpt.log) 与[分类证据](GUI_shutdown_warning.json) 保存原行范围、全日志 SHA256 和退出证明。1048.746 s 的 `omni.kit.window.property` shutdown 后，`app_menu._build_menu → file_menu.can_close → omni.usd.get_context().get_stage_state` 因 context=None 抛出 AttributeError；该特定回溯属于 GUI teardown，原 supervisor 最终 `Popen.wait` 为 exit 0。没有据此声称整份日志没有其他 warning，也未修改环境。

`real_calibrated=false`、`native_pair_success=null`，原 `NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT` 与 `NATIVE_TARGET_OVERLAP_UNAVAILABLE` flags 保留。有效 cooked 碰撞几何全局误差、原生速度与真实标定边界仍未独立核清。本次 CPU 审计没有 GPU/API、新执行或门槛修改。
