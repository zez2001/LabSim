# teacher baseline-close01：首次接触前闭合轨迹对照

2026-10-27。原始独立结论为 `task_success=false / TASK_INCOMPLETE`，不是完整成功。真实进程 PID 602515 已退出，exit 0、wall 1155.825719 s；运行代码 `76936e10a6abcbb34b4c82b4116ce15f363730fb`，实际 124.266667 s / 7455 转换。`record_valid / record_integrity_valid / physics_trustworthy=true`，成功 BC 资格 false。

本次 v6 显式 `near_contact_slow_close_enabled=false`，实际首次双侧接触前的近接触总开口闭合速率为 **20 mm/s**（约 0.333333 mm/tick），v5 preorient01 对应为 **2 mm/s**。取消的是 v3 增加的前置限速；首次接触 freeze、持久窗口、失触后 2 mm/s、force-hold v2、8 N 上限、机器人/材料/评分参数均未改变。保存配置仅差该布尔值与两个控制器版本标签；七组 physics/vessel/robot/gripper/acceptance/cameras/robot_tracking 相等，四份基础及派生 scorer 源码逐字节相同。该提交另含静态公共机器人标定与 prompt v4 文本，确定性 teacher 不消费 task_language；实际命令直接复核于 [mode_and_reference_contract.json](mode_and_reference_contract.json)。

实际首双侧接触从 v5 的 18.633333 s 提前到 **18.05 s**，冻结目标由 10.401166 mm 变为 **9.666667 mm**。这是闭合轨迹导致的实际目标与测量指力变化，不是提高 effort cap 或修改压缩配置；既有配置中的压缩参数也不能当成全部实际关节目标差的全局上界。v6 没有触发额外 force-hold 慢闭或 release-slew 分支，确认抓持时最弱测量指力约 0.765045 N；随后确实发生普通显式开爪，并通过实际脱指和撤离判据。

原独立抓持窗口最大杯底相对漂移为 **19.511679 µm / 0.0214122°**，低于原 200 µm / 1°；配置抓点 anchor 最大 2.827610 µm。完整五项最大值已逐物理样本复现，峰值和参考见[保持审计](../teacher_baseline_close_01_preload_audit/summary.json)。这些是原有有界抓持评分窗口的仿真数值，包含杯底旋转杆臂，不能解读为释放后仍保持于手内或硬件精度。

v5 的双侧参考建立在 EXTRACT 前 0.754167 s，v6 在前 **0.770833 s**；两轮均不是提取之后才建立参考。v6 提取前缀不再越过 200 µm，抓持、来源槽清空与搬运均通过。generic grasp04 曾在抬升后才形成参考的限制仍原样保留，不能把不同参考时序的指标混作等价对照。

![闭合提取前缀对照](extract_orientation_ab.png)

完整装载仍失败的原因是：真实底部支撑形成后，杯在目标平面上的 XY 误差已大于原 100 µm，缺少 `correct_target_supported` 独立事件。原 candidate/release/retreat 与撤离后 3 s 稳定均 true，不覆盖此缺项。见[支持→开爪判据审计](../teacher_baseline_close_01_support_gate_audit/README.md)。

[闭合全读审计](../teacher_baseline_close_01_closed_read_archive.json) 读取 40 个唯一 H5 dataset、核对 7455 转换时序与标签，正常 ACT / DP failure batch 实际通过，success 过滤拒绝，H5 无外部数据依赖。183 个原非 raw SHA 不变，两份 raw 无损归档由 1,784,582,960 B 减至 266,851,851 B，释放 1,517,731,109 B。未改原 H5、标签、视频、证明、门槛、runtime 或策略输入，未执行 GPU、API 或训练。
