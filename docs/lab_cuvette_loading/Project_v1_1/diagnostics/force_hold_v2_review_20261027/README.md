# force_hold v2 独立源码审查

审查对象是未提交草稿的源码快照，SHA256 与实际 CPU 例见 `review_snapshot.json`。本审查没有修改运行时、配置、资产或账本，没有 GPU/API/H5 操作。以下均为软件行为检查，不是物理效果证明。

## 明确阻塞：低于 2 mm 的合法旧目标会被主动打开

公共动作允许总开口 0–80 mm，旧 helper 的首次冻结可能保留低于 `minimum_total_opening_m=2 mm` 的已有目标。新 force_hold 使用 `max(2 mm, min(frozen, previous)-speed*dt)`，在低力持续确认后把 0/1/1.99 mm 的已有目标分别打开到 2 mm，违反“永不主动张开”。同时 `force_hold_applied=false`，决策仍显示 `hold_contact_target`，未标出这次张开。

建议最小修正只为这条新增分支增加不超过已有 `min(frozen,previous)` 的上界，并补充 0、1、1.99 mm 回归；不需要改变公共开口范围或原有 caller 契约。

## 教师卸载起点需要集成检查

新增 force_hold 可以收紧实际 applied target，但父 teacher 的 `latch_opening` 仍是旧目标。SUPPORT_TRANSFER 从旧 latch 插值，首次 logical widening 又会优先采用该 ramp，可能跳回旧目标附近。实际 helper CPU 例仅收紧两个 tick 后，父计划首卸载增量是 1.723 µm，而 helper 下发开口增加 68.393 µm。

这不意味着所有公开 policy 卸载都有相同错误：公共 facade 已从 `task.grip` 的实际 applied target 开始插值。本项针对直接 teacher 与新共享 helper 的边界，须记录真实卸载起点；不能只凭新增分支已被禁用，就宣称卸载仍是原速慢开。

## 已核实的边界与兼容性

- 有 2 mm 目标硬下限和 2 mm/s 速度约束，并非数学上无界闭合。但 `maximum_compression_m` 当前只参与派生约 0.310219 N 的目标，不是累计 `measured-target` 压缩差的硬上限。持续低力 5 s 的软件例可闭到 2 mm，静态 measured-target 差约每指 4.364 mm；这不等于实际材料压缩或穿透，却是需声明的传感失配/不可达力目标风险。
- 同一时刻重复 100 次没有额外闭合。低 cap 和显式张开关闭新增 force_hold；无 cap 的旧调用动作路径保持原有行为。既有 contact-loss 恢复不是本次新增规则，不应将“低 cap 禁止新增力维持”描述成“低 cap 禁止一切旧闭合行为”。
- cap 从实际阶段 `effort` 标量传入；派生力目标按每指计算。输入没有相位或物体姿态，未发现真值越权。gain、摩擦、质量假设和评分没有因 helper 新分支改变。
- 既有显式开口 ramp 到终点后若仍存在双侧残余接触，下次同 logical 请求可能再冻结；该边界在 v1 已存在，本审查不建议为新功能顺带扩展规则。

现有 force_hold、gripper、joint 和 tracking 集成共 58 项 CPU 测试通过，但没有覆盖上述低开口反例和 teacher 卸载起点。完整回归应针对最终稳定快照另行记录，不能用这 58 项通过放行缺失边界，也不能称力维持已经过物理验证。
