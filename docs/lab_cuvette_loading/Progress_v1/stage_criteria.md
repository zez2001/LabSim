# 阶段、窗口和终局语义

实现依据为 `core.ProgressEvaluator`。几何、判定阈值和归一化尺度独立存储；最终数值及每项来源以本集 `progress_config.resolved.json` 为准。下表定义 Progress 事实，不覆盖原独立判分。

| 阶段 | 当前物理条件与证据 | 确认／回退含义 |
|---|---|---|
| approach_grasp | 实际 TCP 到合法抓取点的位置及静态抓取姿态；已验证接触抓持也构成到达证据 | 接近与抓持分开；新增接近诊断门槛 5 mm、10° |
| grasp | 合理实际开口、双侧接触 ≥0.01 N 持续 0.1 s、可核实相对位姿；建立本次参考并跟踪滑移 | 在架内仅说明抓持候选；离架另验。实际抓持质量可回退；历史保留 |
| extract | 同次有效抓持中，完整底部包络高于来源架口至少 2 mm | 倾斜使用最低点；中心变高不足以确认 |
| transport | 当次已验证离架，持物相对初始位置 XY 横移至少 50 mm，再到固定预插入点 3 mm 半径区域 | 空夹爪到达不确认；原 held_transport 横移事件与到达目标分开 |
| align | 正确任务装载参照的 XY、倾角、绕轴角及当次持物路线证据 | 使用明确诊断预算，不默认方形等价旋转。loaded-pose 候选预算与最终稳定判据分列 |
| insert | 正确目标归属、姿态和同次持物 lineage；实际深度达到配置目标减原几何容差 | 归一化深度可 clip，原深度保留负值；到深度不等于承托 |
| support_transfer | 正确目标底部力 ≥0.1 N、底部间隙绝对值 ≤50 μm、深度到位、目标归属及观测输入材料重叠 ≤50 μm；首次取得承托还要求 loaded-pose 对准条件 | 首次交接后，持续承托姿态改用原释放后直立门槛 ≤1°，不持续套用控制对准预算。原座全力模长不能替代底部承托 |
| release_retreat | `released`：双侧力低于接触门槛、实际双指充分张开并持续 0.05 s，且合法目标承托；`retreated`：实际整手几何净距达到 40 mm | 合法支撑交接不算抓持丢失；脱指和撤离独立记录，TCP 距离仅辅助 |
| stable_complete | 正确目标、承托、脱指、撤离、保留深度、直立及几何质量持续成立；实际位姿漂移和旋转受限 | 读取原 `demo_release.observe_s=3 s`、位置漂移 ≤0.2 mm、姿态变化 ≤1°；条件中断重置连续窗口，保留中断事件 |

## 三层状态

1. `stages[*].current_satisfied` 是当下三值条件：true／false／null。`status` 区分未开始、进行中、当前满足、回退和证据缺失。
2. `milestones` 保存 `ever_achieved`、`first_candidate_t`、`first_confirmed_t` 及当前状态。未来确认不会回写过去标签。历史覆盖率为九阶段固定等权计数。
3. 每次抓持独立重建内部相对参考；`attempts` 输出当次最大相对变化、阶段确认时间、开始／结束时间、结束原因、success／failure／interrupted／incomplete 及前后重试关系。合法释放时结束抓持区间，`end_t` 为该时刻；若随后完成稳定窗口，该尝试的终局结果更新为 success，并另存 `stable_complete_t`。内部参考位姿本身不重复写入尝试列表。尚在执行不立即判失败；终局未进入阶段标 `not_reached`。

承托状态：`source_supported`（来源几何支撑候选）、`gripper_held`、`target_supported`、`unsupported_or_lost`、`unknown`。来源支撑在缺少独立力归属时明确保留几何证据范围。

## 连续值与归一化

位置、旋转等误差用声明的固定尺度 `clip(1-error/scale,0,1)`，深度用 `clip(raw_depth/target_depth,0,1)`；源净空、支撑、撤离和稳定各有独立尺度。连续值仅展示诊断质量。`current_stage` 的选择基于当前物理条件，`highest_ever_stage` 表示历史最高阶段，二者可不同。合法释放后的 grasp、extract 或严格 align 当前值可以为 false；stable_complete 使用自己的持续物理条件，不要求九个阶段当前值同时为 true。

## 终局分析

`termination_domain` 描述正常、超时、安全、服务、执行、仿真、记录或中断等结束域。`unfinished_requirement` 是下一项未满足要求，不等于实际失败事实。`failure_observation` 只记录有证据的抓持丢失、接触停滞、释放后失稳等事件。

卡滞必须有实际执行请求、命令向下变化、实际深度增长不足、孔壁接触和完整时间窗口；深度恒定本身不足以归因。原任务终止原因、安全事件、物理告警与最终资格原样保留。

Progress 与原最终 scorer 的比较应查看事件输入和门槛。原 scorer 仍是完整任务成功与数据资格权威；对差异报告，不反向改历史结果。
