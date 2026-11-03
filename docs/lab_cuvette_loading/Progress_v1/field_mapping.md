# 输入字段及几何映射

当前实现：[`core.py`](../../../demos/lab_cuvette_progress_v1/core.py)、[`geometry.py`](../../../demos/lab_cuvette_progress_v1/geometry.py)、[`config.py`](../../../demos/lab_cuvette_progress_v1/config.py)。字段实际来源为 [`PhysicsRecorder.capture`](../../../demos/lab_cuvette_env_v1/physics_capture.py)。world 是 Isaac 米制 Z-up；四元数为 wxyz。配置逐项来源写入 resolved JSON 的 `sources`。

| 指标或判据 | 原始输入／参照 | 坐标系、单位 | 频率及证据 | 缺失处理／代码 |
|---|---|---|---|---|
| 抓取接近位置、姿态 | `actual_tcp_position_m`、`actual_tcp_quaternion_wxyz`；器皿位姿与 `robot.grasp_above_bottom_m`、固定抓取方向 | world，m、rad | 物理 240 Hz；实际 TCP，非计划 waypoint | unknown；`geometry.measured_geometry` |
| 实际开口、双指接触 | `finger_joint_positions_m`、`finger_contact_N` | 两个单指位移 m；力 N | 240 Hz；两个实测关节和力张量 | unknown；`core.ProgressEvaluator.update` |
| 抓持相对位移、旋转 | `cup_in_hand_position_m`、`cup_in_hand_quaternion_wxyz` | panda_hand 局部，m、rad | 240 Hz；本次有效抓持建立的参考位姿 | 未建参考或姿态缺失为 unknown；`core` |
| 接触持续时间 | 双侧实际力与递增 `t` | s | 物理时间；采样断层中断持续计时 | 不从 phase 推断；`core` |
| 器皿底部与离架净空 | `object_bottom_world_z_m`（兼容旧 `source_bottom_z_m`）；来源架口 world Z | world，m | 240 Hz；实际全部视觉顶点变换后的最低 Z，包含倾斜 | 优先实际包络，再使用已核实 body-local bounds；无依据则 unknown；`geometry` |
| 固定预插入距离 | 器皿底部参考位姿；`layout.target_floor`、目标深度和 `preinsert_bottom_above_rim_m` | world 装载参照，m | 240 Hz；不随当前进展移动目标 | 无几何或位姿为 unknown；`geometry` |
| 持物搬运 | 底部净空、当次抓持、实际 XY 位移、固定预插入距离 | world，m | 240 Hz；离架及持物 lineage；空手距离仅诊断 | 证据不满足不确认；`core` |
| XY、倾角、绕轴角 | 实际器皿位姿、原座到装载轴偏移、仪器旋转；兼容 `xy_error_target_m`、`tilt_deg`、`yaw_error_deg` | task loading frame，m、rad（原字段 deg 显式转换） | 240 Hz；不默认采用方形四重对称 | unknown；`geometry` |
| 轴向深度 | `depth_m`；或器皿底部参考投影到装载轴，`geometry.target_depth_m` | 入口 0，向内正，m | 240 Hz；入口外保留负值 | 不用深度单独确认成功；`geometry`／`core` |
| 目标归属、输入材料重叠 | `target_region_contains_object`、`input_geometry_overlap_observed_m`；源记录另有 sample time/cache age | 所选原座；m | 物理行包含约 15 Hz 缓存的几何查询；含 source scope | 未获得查询结果则 unknown；横向明显远离时可判不在目标内。接受上游查询的 bool 结论，保留其符号限定，非 cooked 全局无穿透证明 |
| 目标底部承托 | `target_bottom_support_N`、`target_bottom_gap_m` | world 向上底部力 N，间隙 m | 240 Hz；已分类底部接触点；不是全座力模长 | unknown；`core`；对照 `Size_v1.scorer._window` |
| 实际释放 | 两个实际关节开口和双侧力 | 单指 m、N | 240 Hz；连续 0.05 s（原 scorer） | 无任一通道为 unknown；`core` |
| 整手撤离 | `gripper_object_clearance_m` | world，m | 240 Hz；panda_hand 和双指输入顶点 AABB 分离距离的保守下界 | unknown；不由 TCP 距离替代；`core` |
| TCP 辅助距离 | 实际 TCP 与器皿刚体原点 | world，m | 240 Hz；中心距离，非几何净距 | unknown；`geometry` |
| 连续稳定 | 实际器皿位置／四元数、正确目标承托、脱指、撤离、深度和输入几何 | world，m、rad、s | 240 Hz 因果窗口；中断后重新计时 | 缺证据或断层不确认连续稳定；`core._stable` |
| 原生速度、差分速度 | `linear_velocity_native_m_s`；逐物理步实际器皿刚体原点差分 | world，m/s | 240 Hz；同一步结束；另保留原 COM 差分原记录 | 初步差分 unknown；不将原点与质心速度混称；`core` |
| 卡滞观察 | 已执行 action、`commanded_bottom_z_m`、实际深度、`wall_contact_N` | world Z／深度，m、N、s | 因果持续窗口；命令 FK 仅请求证据，非实际运动 | 请求或接触缺失不宣称卡滞；`core._stall` |
| 控制动作区间 | H5 `timestamp`、`next_timestamp`、`obs_step`、`next_obs_step`、动作及 `control_auxiliary` | episode 时间，s；4 个物理步／60 Hz 控制周期 | `before=t_obs`、`after=t_next`；事件归 `(t_obs,t_next]` | 缺精确采样端点显式 unavailable；`io.ProgressWriter.transition` |

## 固定参照与来源

| 参照 | 当前来源与定义 |
|---|---|
| 来源槽 | 优先取 `progress_input_metadata.json` 的实际 `layout`，否则调用配置指定的 scene layout（当前为 `demos.lab_cuvette_size_v1.scene.layout(cfg)`）；完整架 A1；槽位随 rack 变换 |
| 来源架口 | layout 的 `source_rim_z`；离架使用实际最低底部包络 |
| 器皿原点、底部、顶部 | 在线 recorder 的实际 body-local visual vertices min/max，保存至 `progress_input_metadata.json`；历史轨迹按 registry 已核实 bounds。缺失不假定根节点为底部 |
| 合法抓取区域 | 配置 body-local 抓取参考点 `[0,0,robot.grasp_above_bottom_m]`，当前 Z=0.053 m。配置记录 ±5 mm 的诊断带；当前接近判据实际使用 TCP 到参考点的三维距离 ≤5 mm，静态抓取姿态误差 ≤10° |
| TCP | `panda_hand → right_gripper`，配置位移 `[0,0,0.1] m`、四元数 `[0,0,0,1]`；原 capture meta 有 Lula FK 验证 |
| 原目标座 | `candidate_far_hinge`；原座 floor 保留；目标加载 floor 按 seat 局部偏移 `[0.00065,0.000001,0] m` 随仪器一起变换 |
| 目标入口、轴、深度 | loading floor 沿装载轴上移配置 `target_depth_m=0.027`；入口处深度 0、向内正 |
| 预插入点 | 固定入口之上配置 `control.preinsert_bottom_above_rim_m`，不拟合未来轨迹 |
| 撤离几何 | 原 recorder 对三个手爪链接输入几何做 AABB 分离下界；正式门槛读取 `acceptance.actual_retreat_clearance_m=0.04` |

原生接触回调保留冲量 Ns 与按本集 `physics_dt` 换算的 N；Progress 不将回调力再加到已按 `physics_dt` 返回的接触张量。回调是稀疏事件通道，缺事件不等于零力。

历史 `phase`、Teacher state 和 `task_events_json` 只用作时间对照；Progress 判据从实际状态重算。原 scorer 的 `bilateral_grasp_observed` 是持续双侧接触，`held_transport_observed` 是持物横移历史证据，**并不证明已到固定预插入点**。新增 transport 完成还要求固定目标距离。
