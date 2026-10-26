# 机器人状态跟踪补偿接口与任务接入

`demos.lab_cuvette_project_v1_1.robot_tracking.RobotTrackingCompensator` 是只依赖 NumPy / SciPy 的数值控制辅助模块。它不导入 Isaac、不推进仿真、不读取器皿真值，也不改变 PD、摩擦、碰撞或判分。Project_v1_1 配置显式启用此接口，任务在每个控制步最多更新一次估计，预检期间只读取冻结估计。当前已完成 CPU 数值测试；真实物理验证结果以独立运行记录为准。

输入必须来自同一世界坐标系、相同 TCP 定义和同一控制步边界：

- `previous_command_position_m / previous_command_rotation_matrix`：上一控制步实际下发的、经过限速后的关节命令的 FK；包括此前已经应用的补偿。不能使用未执行的原始 IK 解。
- `actual_position_m / actual_rotation_matrix`：上述命令作用后，同步测得的机器人 TCP。位置单位米，姿态为正交的 3×3 主动旋转矩阵。
- `nominal_position_m / nominal_rotation_matrix`：本步原本计划下发的笛卡尔目标。
- `dt_s`：本次新观测对应的实际控制采样间隔，单位秒。

位置可观测误差为 `previous_command_FK - current_actual_TCP`。旋转误差使用世界系 `Log(R_previous_command · R_actualᵀ)`。一阶低通默认时间常数 0.1 秒，系数为 `1-exp(-dt/0.1)`；也可以显式选固定 `alpha=0.2`。模块不另加积分器或 PI 项。

滤波后按向量范数将位置偏置限制在 1 mm、角度偏置限制在 2 mrad，并将有界值写回滤波状态，避免大瞬态留下隐性无界长尾。调用者可进一步降低这两个上限，不能提高。输出为 `p_nominal + bias` 和 `Exp(rotation_bias) · R_nominal`。这两项限幅是数值控制上限，不是实物或仿真精度指标。

```python
from demos.lab_cuvette_project_v1_1.robot_tracking import RobotTrackingCompensator

observer = RobotTrackingCompensator(time_constant_s=0.1)
result = observer.update(
    nominal_position_m=nominal_p,
    nominal_rotation_matrix=nominal_R,
    previous_command_position_m=previous_applied_command_fk_p,
    previous_command_rotation_matrix=previous_applied_command_fk_R,
    actual_position_m=measured_robot_tcp_p,
    actual_rotation_matrix=measured_robot_tcp_R,
    dt_s=1 / 60,
)
# result.command_position_m / result.command_rotation_matrix 是候选目标。
# result.diagnostics 可直接写为 JSON；没有执行动作或改变场景。
```

`hold(...)` 在没有新配对观测时重用估计，既不增加样本计数，也不重复更新滤波器；它不表示冻结机器人或器皿。`reset()` 清除全部偏置和计数，应用于新 episode 或坐标定义改变之后。输入非有限、矩阵不合法或时间间隔无效时，在改变估计状态前抛出 `ValueError`。

诊断字段保留原始位置/旋转误差、限幅前滤波结果、实际偏置、范数、饱和状态、滤波系数、时间间隔和样本数；明确记录 `uses_object_truth=false`、`numerical_control_aid=true`、`real_calibrated=false`。

CPU 测试覆盖固定扰动简化被控对象、动态滞后与斜坡、噪声、世界系旋转组合、刚体坐标变换、范数限幅、瞬态恢复、采样间隔、hold/reset 及非法输入。简化被控对象的数值表现不能替代 Isaac 物理验证，更不能代表真实机器人校准结果。当前接入只影响新版本；历史配置与输出保持原样。任务保留 nominal reference 与 effective IK goal 两套记录，实际运行保护仍比较 nominal reference。反馈启用后每步重新求连续 IK，不直接执行冻结预检关节数组。
