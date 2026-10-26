# teacher preorient01：空爪朝向修正后的闭合对照

2026-10-27，仅 CPU 分析已关闭输出。对比 v4 `teacher_lateral_hold_01`（109e637）与 v5 `teacher_preorient_01`（f7e1bcc），两轮原始标签均为 `task_success=false / GRASP_SLIP`。v5 的真实退出证明为 PID 421878、exit 0、process wall 206.592147 s；实际结束于 20.05 s / 1202 转换。原 `record_valid / record_integrity_valid / physics_trustworthy=true`、BC false、post-retreat unavailable/null 均保留。

空爪姿态修正已实际生效。GRASP 边界均为 14.516667 s，此时杯仍直立且双指无接触：TCP 下轴相对 world-down 的倾斜由 **0.05454518° 降为 0.000210434°**；完整 TCP 四元数相对静态 `Rz(yaw) Rx(pi)` 理想朝向的误差由 **0.05653719° 降为 0.000362046°**。下轴倾斜与完整三维朝向误差分别记录，避免把 yaw 混为工具倾斜。这些是当前仿真状态数值，不是硬件姿态精度。

但双侧抓持参考建立时，杯体倾斜仍为 **0.264280°**（v4 为 0.263936°）。EXTRACT 开始时分别为 0.240289° 与 0.253322°。参考建立后的 GRASP 段最大杯底相对漂移为 v5 20.945 µm、v4 8.823 µm；两轮全局首次越过原 200 µm 门槛都发生于 EXTRACT，而非 GRASP。

v5 首次越界在 **19.5375 s，EXTRACT 后 54.167 ms**；v4 为 19.533333 s、后 50 ms，差一个 240 Hz 物理 tick。v5 当时杯体世界朝向已变化 0.244138°，实际 hand 只变化 0.000898°，名义四元数在整个提取前缀保持不变，XY 仍固定。第一越界落在真正执行区间 `(19.533333, 19.55]`，该区间与后继响应分开，不用“最近控制点”代替先后关系。

最终 v5 原评分的杯底相对漂移最大 **1.541226 mm / 1.504271°**；配置抓点 anchor 最大 210.052 µm，轴向 146.496 µm、横向 150.625 µm。v4 对应杯底 1.520247 mm / 1.752554°。杯底指标包含旋转杆臂，不能称为纯轴向滑移。v5 source-slot-cleared=false，未装载、未开爪或撤离。

力保持 v2 确实工作：共四个低测量指力慢闭 tick，每次 33.333 µm、总 133.333 µm，均在原反馈速率与预算内；没有执行释放 slew。反馈之后指力恢复，但杯体摇摆仍继续，不能概括为整个提取段持续低力，也不能据版本名宣称释放路径已通过。完整五项抓持最大值已由全 raw 重算并匹配原分数，见[独立保持分支审计](../teacher_preorient_01_preload_audit/summary.json)。

![闭合提取前缀对照](extract_orientation_ab.png)

此固定场景单次配对支持的结论是：**消除这项空爪接近姿态残差，仍不足以通过该教师抓取/提取回归。** 不能扩大为姿态完全无贡献、其他状态下无效、广泛成功率或已确定全部物理根因。原 200 µm / 1° 门槛未改变；physics、vessel、robot、gripper、acceptance、cameras、robot_tracking 七组保存配置相等，完整配置只差两个 controller version 标签，三份 scorer 源码在两次提交之间逐字节相同。

[stage_pose_and_source_contract.json](stage_pose_and_source_contract.json) 保存阶段边界真实四元数、杯倾斜、全局首次越界、配置差异和源码 SHA。[summary.json](summary.json) 与两份 CSV 保存逐物理 tick 的杯/hand/命令 FK 旋转及真实执行区间。两轮全部解压物理行的 SHA 和长度均与归档前一致。

[闭合全读审计](../teacher_preorient_01_closed_read_archive.json) 已读取 40 个唯一 H5 dataset、核对 1202 转换时序与标签。正常 failure 过滤真实 ACT / DP batch 读取通过，success 过滤拒绝；无 H5 外部数据依赖。95 个原始非 raw 文件 SHA 不变，两份 raw 无损归档释放 219,108,284 B。未改原 H5、标签、视频、退出证明、代码、阈值或策略输入，未启动 GPU 或 API。
