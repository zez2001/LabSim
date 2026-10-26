# teacher_camera_v2_01：抓取前接近速度保护停止

本次已真实关闭、进程exit0；仿真在 **6.016667s / APPROACH_SOURCE** 因`EXECUTOR_ACTUAL_SPEED_LIMIT`停止。没有进入GRASP、EXTRACT、装载或释放。

原始判分保留：`failure_type=EXECUTOR_FAILURE, failure_domain=executor, task_success=null, record_valid=false`；同时`record_integrity_valid=true, physics_trustworthy=true`。这是执行器速度契约不满足，不能改写为有效装载失败、任务false或物理解算器无效。没有`PHYSICS_INVALID`结论。

## 直接证据

最后控制步的名义参考速度为 **50.092589mm/s**，实际TCP差分速度为 **50.096555mm/s**，均高于未修改的50mm/s保护限值。最后名义跟踪位置误差为41.396809µm；实际速度基本跟随了已经过快的名义下降，而不是凭空出现213mm一类跳支异常。

旧APPROACH_SOURCE采用6s的cubic smoothstep。根据本次记录的实际起点和来源器皿位置加53mm名义抓取高度，位移约226.852859mm；该曲线峰值公式为`1.5×距离/时间`，理论峰值 **56.713215mm/s**。尚未执行的后半程不能计为实际运行。它说明原始时间安排与新版本50mm/s guard不相容，后续修复应调整teacher运动阶段时长，不能靠提高guard或改物理参数放行。

![名义和实际速度](nominal_actual_speed.png)

360控制步 / 1444物理步（含reset），物理记录1445行从step0连续。无已记录机器人环境禁碰，双指接触力均0N，实际和下发总开口约80mm，器皿仍由来源架支撑。原始terminal_window中的“stable”只是中止前器皿在来源架的末窗口；`post_retreat_window=unavailable, stable_after_retreat=null`，不能充当放置后稳定证据。

`control_speed_trace.csv`包含全部360步名义/实际速度、TCP、跟踪误差、开口、接触和停止标志；`summary.json`记录原标签与解析公式。`original_*`为未修改的小原始证据，SHA256见manifest。

本轮只做闭合记录的离线分析，无API/GPU、未读H5、未改原始输出或控制/物理配置。下一次teacher完整流程仍待实际运行，不能从这条抓取前录像推断闭爪、搬运或插入质量。
