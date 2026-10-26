# GPT debug03：闭合数据与碰撞离线审计

2026-10-27，仅 CPU 读取已关闭记录。实际运行代码 `109e637bcb264458ffc231f4e052e60ff6764242`；PID 398972 的真实退出证明为 exit 0，读取前 PID 已不存在。此轮为独立标准 reset 的 debug，使用 prompt v3、context4 与原共享费用 ledger；不是正式五轮，也不表示教师回归通过。

原始结论保留为 `task_success=false`、`SAFETY_COLLISION / ROBOT_ENVIRONMENT_COLLISION`，`record_valid / record_integrity_valid / physics_trustworthy=true`，`success_bc_eligible=false`。共 15 次 API 决策、15 个接受动作、1779 个控制转换，终止时间 29.666667 s。原始全程 `grasp_success=false`、`transport_success=false`；观察到离开来源槽与持物横向移动，不能据此改写全程资格。未插入、交接支撑、开爪或撤离，`post_retreat_window.status=unavailable`、`stable=null`。

## 碰撞时序

首个原生 forbidden 接触在 **29.654167 s / physics step 7117**，双方为 `/World/Franka/panda_leftfinger/geometry/panda_leftfinger` 与 `/World/Instrument/Collision/SourceMesh2`。首接触点为世界坐标 `[0.0729642212, -0.1194274351, 0.9377999902] m`；随后共四个接触事件直到最终 step 7120。没有观察到离架后的正冲量杯体—仪器接触。

已建立抓持参考后、首个已知碰撞前，合格双侧接触样本的杯底坐标系相对位移最大 **2.068 µm**；29.650000 s 时仅 1.567 µm。第一次超过原 200 µm 门槛与首碰撞位于同一 tick（252.870 µm），最终增至 **841.508 µm**。因此不能把终值解释为碰撞前已经滑脱；也不能用碰撞前较小漂移覆盖原全程抓持失败。杯底相对位移包含旋转杆臂效应，不是单独的轴向滑移或实物精度测量。

末动作请求世界系 `[36,16,0] mm / 2 s`，实际执行 **99/120 tick、1.65 s** 后安全停止；实际 TCP 位移 32.799521 mm，剩余目标距离 **6.602878 mm**。已执行控制边界上的最大位置跟踪误差为 **0.406015 mm**，与停止后的剩余距离分开。接触传感力峰值不等于 4 N 驱动上限，也不构成硬件力标定。

GPT01 同属机身接触安全失败，但首次碰撞是 `panda_hand` 对同一 `SourceMesh2`；GPT03 是 `panda_leftfinger`。首接触点相差 44.098 mm，GPT03 的 z 高 22.337 mm。不能称为相同碰撞形状、相同高度或相同路径。

上述物体真值与接触坐标只用于闭合后的离线诊断，从未送入策略。相机可见性应以实际公开图像及独立 render-only 重建检查；不能用这些坐标制造 GT 裁图。

## 数据完整性与读取

[完整闭合审计](../gpt_debug_03_closed_read_archive.json) 读取 40 个唯一 H5 dataset，验证 1779 条转换的 observation/action/next-state 时序及 15 条回执链。正常 `LabCuvetteProjectV11Dataset` 的 failure 过滤实际完成 ACT 与 DP batch 读取；success 过滤拒绝。未运行训练或优化器。H5 无外部 group link、dataset 外部存储或外部 VDS 数据依赖；元数据中的源路径仅为来源记录。

102 个原始非 raw 文件的 SHA 全部保持不变。两份 raw JSONL 无损 gzip 归档后，逐字节解压 SHA 与长度均相等，合计由 400,410,364 B 减为 59,392,761 B，释放 341,017,603 B。完整物理 7121 行、原生接触 36030 行已流式复核。原 H5、标签、视频、退出证明及模型观测文件均未改动。

[实际公开输入交叉审计](wire_inputs_cross_audit.json) 将兄弟审计复制的 67 个源文件逐一与归档前保护 SHA 和当前源 SHA 比对，73 个复制文件的 SHA/长度均通过，包含原 `gpt_control` 的全部 63 个文件：15 份公开观测 JSON、30 张 exact JPEG，以及持久化的静态 prompt/schema、公开工具调用、回执、controller 与 trace。**保存范围不是完整 HTTP 请求 body 或完整模型 memory response-item 组，未保存私有 reasoning。** provider 返回模型名按原日志保留，不主张独立验证上游身份。

## 小证据入口

- [summary.json](summary.json)：原标签、原评分、首接触、首次越界、终值复现、GPT01 对照与来源 SHA。
- [collision_window_physics.csv](collision_window_physics.csv)：碰撞前后 0.5 s 的逐物理 tick 状态。
- [正常 reader 结果](../../validation/gpt_debug_03_normal_reader.json)：真实 ACT / DP failure batch 与 success 拒绝。
- [实际公开观测与图像](../gpt_debug_03_perception/README.md)：保存范围、逐动作回执及全部公开图片。
- [render-only 三状态](../../camera/render_only_closed_states_01/gpt03_states.json)：initial、闭爪后、decision000014 动作前；真实 q9 / 杯体 pose 与 H5/raw/public 对齐，只为重建相机检查，不是新执行证据。

本审计未启动 GPU、未调用 API、未改 runtime、阈值、原数据或策略输入。结果不支持完整装载成功、广泛成功率、硬件精度或跨平台动力学精度结论。
