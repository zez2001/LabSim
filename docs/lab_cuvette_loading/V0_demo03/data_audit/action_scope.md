# 动作范围与阶段化夹爪控制

本轮 H5 主 `actions` 为 8 维：7 个绝对机械臂关节位置目标（rad）及 1 个夹指关节位移目标（m）。源码直接保存 `ArticulationAction.joint_positions[:8]`，即九维命令的前七个臂关节及左指目标；当前执行器给左右指下发对称命令，右指第九维保留在物理记录 `command_q[8]`。它不是 TCP 增量、力矩或双指总开度，也不包含夹指 effort cap。H5 动作属性 `absolute_7_arm_rad_and_symmetric_finger_metre` 与此命令范围一致。

`agent_pose` 同样是实测 `joint_positions[:8]`，第八维是左指实际关节位置，**不是两指均值，也不是两指开距**。左右实际位置受接触影响可略有不同，不能因目标对称而假定实测状态对称；完整九维实际关节位置保留在 H5 `joint_positions` 和物理记录 `joints`。

支撑交接沿用阶段化夹指上限和轴向卸载。每个物理步的gripper_effort_limit_N、gripper_target_m、phase、command_q及实际关节和力均保留于原始physics_records.json；主片完整控制CSV/NPZ通过相同后继时间戳join这些字段，验证见random8000_trajectory/export_checks.json。H5含phase_code但没有单独effort cap序列。后续物理动作回放或策略评估应复用相同的阶段调度或显式读取这些辅助通道；仅重放8维joint targets不能被称为完整重放本轮卸载控制。

本次实际验证了现有MinimalPickDataset读取关节动作训练格式batch，没有训练、策略推理或验证一个仅靠8维输出即可独立完成任务的学习策略。适配任务独立成功与数据资格描述本轮真实记录和明确控制范围，不代表自主策略性能。

正式批次只读工具 `audit_formal_batches.py` 会将每条 H5 动作和同一后继物理步的 `command_q[:8]` 按写入时 float32 转换逐元素核对，核对左右下发命令对称、`agent_pose` 等于完整实测状态前八维、阶段及时间点相符，并确认辅助 effort/原始 grip_target 未缺测。它报告辅助通道范围，不把“batch 可读取”提升为“8 维动作已经包含全部控制”。
