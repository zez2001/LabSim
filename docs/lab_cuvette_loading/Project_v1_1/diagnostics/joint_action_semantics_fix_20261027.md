# 公共关节目标保留修复

2026-10-27。此前只读审查和反例完整保留在 `joint_action_semantics_review_20261027.{md,json,py}`，没有改写其中的历史发现。

## 改动

仅修改 `tasks/lab_cuvette_loading_project_v1_1.py`。公共 `joint_position` / `joint_velocity` 请求经 facade 包装为低层 EE/FK 参考时，task 使用原始 `raw_model_action.type` 识别其关节来源：保留 `_executor_q7`，按其未改变的名义 FK 参考复核，不再施加 Cartesian 补偿或重新 IK。执行仍保留名义 `reference_TCP`，因此原有实际 TCP 跟踪、速度及关节检查继续生效；现有 `GenericContactHold`、夹爪开口与力限调度不变。

公共 EE 和直接 teacher EE 路径继续使用已有机器人状态补偿。转换记录及 execution trace 增加 `origin_type`、`compensation_applied`、`joint_target_preserved`，便于区分原始动作类型、是否使用补偿、是否保留关节目标。没有修改 facade、ACT/DP adapter、collector、物理配置、评分或旧版本实现。

## 运行中的实验保护

先独立核实 `teacher_camera_v2_02/process_exit.json` 的 `process_exited=true`、PID 75973、exit code 0，再核实 `/proc/75973` 已不存在，随后才编辑 task。原始 proof 保持不变，SHA256 和核验记录保存在 `joint_action_semantics_fix_proof_20261027.json`。进程正常退出与任务成功是不同事实，本修复记录不据此重判该 episode。

## 已验证与未验证

CPU 回归实际运行 **48 项通过、0 项失败**：17 项新的公共关节动作回归、9 项已有 tracking integration、22 项已有 observer 测试。新回归调用真实 facade 和 task 方法（替换 Isaac 父类的 CPU 桩），覆盖：

- tracking 开启/关闭时，位置和速度请求在 1/4 tick 下精确保留全部七关节计划，包含 FK 冗余分量；joint9 对称手指映射不变。
- 错误 qplan 的 FK 复核在物理推进前拒绝；名义 TCP 跟踪和实际 TCP 速度 guard 仍触发。
- 公共 EE 继续施加补偿；既有直接 teacher EE、每 tick 单次更新、reset 和关闭补偿测试仍通过。
- 连续接触夹爪调节和力限不变；实际 collector `cache_transition` 方法在内存中分别保存原始公共请求、实际 8D actions、实际 9D command、转换和力限。

以同一软件反例重新运行生成 `joint_action_semantics_fixed_20261027.json`：公共关节请求的最大目标改变量从 0.001 rad 降为零，冗余分量保持 0.001 rad；EE 补偿路径保留。该脚本自身只读运行，JSON 中 `runtime_modified=false` 表示**脚本执行没有修改运行时**，不表示此前没有实施本次 task 修复。

这些是软件契约验证，不是 Franka 真实运动学、Isaac 动力学或真实标定结论。本 agent 没有启动修复后的 GPU 实验或外部 API，物理回归须由后续独立关闭的运行给出；历史 H5 和标签完全保留。

复现 CPU 测试：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_lab_cuvette_project_v1_1_joint_action_semantics.py \
  tests/test_lab_cuvette_project_v1_1_tracking_integration.py \
  tests/test_lab_cuvette_project_v1_1_robot_tracking.py
```

测试需要 NumPy、SciPy、OmegaConf、pytest，无需 Isaac、H5、GPU 或 API 凭据。修复前后反例各自记录当时运行时 SHA256，以免将旧结果混作新代码结果。
