# Project_v1_1 关节动作语义只读审查

审查日期：2026-10-27。范围：审查时源码及 CPU 软件反例；没有修改运行时、配置、资产、H5 或历史标签，没有启动 Isaac Sim、GPU 或外部模型请求。审查时 `teacher_camera_v2_02` 正在运行，本次未触碰该进程。

## 结论

**启用 Cartesian tracking 时，公共 `joint_position` 和 `joint_velocity` 请求会被重新逆解，不能保证保留请求的七关节目标或冗余构型。** 这是公共动作契约的问题；直接调用 task 的关节分支没有相同转换。公共动作原始类型仍保存在 `raw_model_action.type`，可以用来区分来源。

建议仅对公共 EE 请求和现有直接 teacher EE 请求启用 Cartesian 补偿。公共关节请求应保留 facade 已校验的逐 tick `qplan`；同时保留该关节计划的名义 FK 参考、现有关节限制、实际 TCP/关节速度检查及夹爪连续接触控制。**不要直接把 facade 的低层类型改成 `joint_position`**：现有 task 的 Cartesian 运行时检查要求 `reference_TCP` 存在，直接关节分支没有该参考。

## 已核实的执行链

以下行号对应同名 JSON 记录的源码 SHA256，而不是未来修改后的源码。

1. `policy/backends/action_adapters.py:3,12-30`：ACT/DP 的 dataset8 定义为七个绝对机械臂关节目标（rad）及单指目标（m）；适配器输出公共 `joint_position`，并将单指目标乘二转为总开口。这不是 EE 增量动作。
2. `demos/lab_cuvette_project_v1_1/environment.py:94-109`：关节位置请求插值得到 `qplan`；速度请求先以当前实际关节状态和请求时长积分，再插值。该路径校验关节范围、速度及相邻命令连续性，并为每个 `qplan` 计算 FK 参考。
3. 同文件 `111-119`：所有公共动作均包装成低层 `ee_pose`，同时保存 `_executor_q7=qplan` 和完整原始 `raw_model_action`。因此低层 `type` 与公共动作类型并不相同。
4. `tasks/lab_cuvette_loading_project_v1_1.py:79-109`：低层 EE 分支不区分原始公共类型。tracking 存在时先改变 IK 目标，再调用 `local_solution`；仅在 tracking 不存在时采用 `_executor_q7`。这会改写公共关节目标，即使 `qplan` 本身已通过预检。
5. 同文件 `110-124`：直接 task 关节分支保留关节命令；两种路径仍共享关节连续性检查及 `GenericContactHold`。同文件 `149-176` 的实际 TCP 跟踪和速度检查只在 `reference_TCP` 存在时执行。
6. `environment.py:169-182`：`target_reached` 明确只衡量实际 TCP 终点，不检查关节目标。因此同一 TCP 的冗余构型改变，或者容差内的 TCP 偏移，可能仍返回 `target_reached=true`；该标志不能证明公共关节契约已满足。

## 实际运行的 CPU 反例

生成脚本、原始结果分别是本目录下同名 `.py` 和 `.json`。脚本调用实际 `ProjectEnvironment.execute` 及实际 task 的转换/guard 源码；以显式 CPU 桩替代 Isaac 父类、机器人和运动学。桩 FK 将 q0–q2 映射为位置、q3–q5 映射为旋转向量，q6 为冗余自由度，执行器理想跟随下发目标。**它不是 Franka 运动学或物理验证，只证明执行链可产生契约反例。**

在一个 1/60 s 请求中，期望关节目标为 `[0.0001,0,0,0,0,0,0.001]` rad。设置已有机器人命令 FK 与实际 TCP 相差 0.4 mm：

- 公共 `joint_position` 和 `joint_velocity`、tracking 开启：`_executor_q7` 保存期望目标，但实际命令为 `[0.0005,0,0,0,0,0,0]`。冗余分量从 0.001 rad 变成零，TCP 终点偏离名义参考 0.4 mm；该反例没有触发现有 guard，且回执 `target_reached=true`。
- 公共 `joint_position`、tracking 关闭：实际七关节命令与期望完全一致。
- 直接 task `joint_position`、tracking 开启：实际七关节命令与期望一致；该路径没有名义 `reference_TCP`。
- 公共 `ee_delta`、tracking 开启：仍施加同一 Cartesian 补偿，符合该补偿的原有作用范围。

上述各例总夹爪开口均为 0.01 m，没有为了构造反例改动夹爪或物理参数。不能据此推断实际 Franka 会产生相同数值，也不能推断现有每条轨迹均受到影响。

复现命令（输出必须为新文件，脚本拒绝覆盖）：

```bash
/tmp/labsim-handoff-ci-py311-20261022/bin/python \
  docs/lab_cuvette_loading/Project_v1_1/diagnostics/joint_action_semantics_review_20261027.py \
  --output /tmp/labsim_joint_action_semantics_review_new.json
```

该命令需要 NumPy、SciPy、pytest，不需要 Isaac 或 API 凭据。脚本依赖仓库现有 tracking integration 测试的 CPU 构造器。

## 原始动作与实际动作记录

`tasks/lab_cuvette_loading_env_v1.py:269-270` 将 `raw_model_action` 写入 collector 的 `raw_output`。`data_collectors/lab_cuvette_env_v1_collector.py:180-198` 的记录关系是：

- `agent_pose`：动作前测得状态的前八维。
- `actions`：转换和夹爪控制后的实际下发九维命令的前八维。
- `next_agent_pose`：后继实际状态的前八维。
- `control_auxiliary/command_q`：完整实际九维下发命令。
- `actions_raw_json`：原始公共动作，含其原始 `type`。
- `action_conversion_json`：低层转换信息。其 `input_type=ee_pose` 只反映包装后的低层类型，需结合原始动作类型解释。

因此现有格式可以如实记录“原始关节请求”和“改写后的实际命令”，不应将此问题描述成 H5 伪造。但 ACT/DP 以实际 `actions` 训练，再经同一公共关节接口执行时可能再次受到 Cartesian 转换，造成动作语义不一致。此审查没有打开任何 H5，也没有判定历史 episode 的实际影响范围；历史结果和标签保持原状。

## 最小修复边界与必要回归

建议在 facade 内部传递可信的原始动作类型，或读取其已有 `raw_model_action.type`。当来源为 `joint_position`/`joint_velocity` 且存在 `_executor_q7` 时，跳过 Cartesian 目标补偿与重新逆解，验证该 q7 的 FK 与未改变的名义参考一致，再原样使用 q7。其余关节边界、连续性、夹爪锁存和 nominal TCP guard 不变。公共 EE 与直接 teacher EE 的补偿、每 control tick 一次采样和 reset 行为保持不变。

落地前需持续 CPU 回归覆盖：ACT/DP8 适配到 facade/task 后七关节目标保持（包含 FK 相同的冗余构型）；速度请求积分及多 tick 插值保持；关节计划的 FK 校验失败不推进物理；原有关节/TCP guard 仍生效；公共 EE/直接 teacher EE 补偿仍有效且不重复更新；夹爪状态与实际九维记录不变。若后续增强回执，可独立报告关节终点误差；现有 TCP-only 回执不能代替该检查。

本次只提交审查材料和软件反例，**没有实施上述运行时修复或声称完成修复后的物理验证**。
