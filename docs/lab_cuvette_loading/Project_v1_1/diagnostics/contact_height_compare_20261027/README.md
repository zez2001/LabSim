# 已闭合抓取接触高度与形状核对（2026-10-27）

结论：`grasp_transport_03` 的 0.826 m 是接近路点，实际闭爪 TCP 为 0.796 m，与 teacher02 同高。三条记录均接触相同杯壁 `band1` 形状，现有证据不足以把 53 mm 抓点判定为不利几何区。原始标签、运行、评分阈值均未修改；仅 CPU 离线审读，未调用 API。

## 初次承载接触（只含非零冲量）

| 已关闭记录 | 右指首接触 t / 杯局部 z | 左指首接触 t / 杯局部 z | 实际 TCP z（右 / 左） | 闭爪驱动上限 | 原始结局 |
|---|---:|---:|---:|---:|---|
| teacher_camera_v2_02 | 18.020833 s / 39.880 mm | 18.041667 s / 58.628 mm | 0.796000 / 0.796000 m | 8 N/指 | GRASP_SLIP，完整任务 false |
| grasp_transport_03 | 21.104167 s / 39.876 mm | 21.120833 s / 58.627 mm | 0.795998 / 0.795998 m | 5 N/指 | POLICY_BUDGET，完整任务 false |
| gpt_debug_01 | 16.504167 s / 36.736 mm | 16.512500 s / 55.486 mm | 0.792859 / 0.792860 m | 5 N/指 | SAFETY_COLLISION，完整任务 false |

杯局部 z 使用实际杯体姿态逆变换到杯底原点坐标，不等同于世界 z、TCP 高度或配置 53 mm 锚点。每条首接触值是该指第一次非零冲量样本的点中位数；左右样本不是同一时刻。teacher02 与 grasp03 首右接触约 39.88 mm、首左接触约 58.63 mm；GPT01 分别约 36.74 / 55.49 mm，整体下移约 3.14 mm。

## 对齐与实际形状

native 回调的 `physics_step` 与物理记录精确匹配，时间误差小于 1 ns；实际 hand 位姿由 measured cup world pose 与 measured cup-in-hand pose 重建，未使用 command FK 替代测量。首接触 hand 局部 z 约为：左 94.378 mm，右 113.114 mm，三条记录一致，说明最早左右触点处于指几何不同高度端。左右触点差约 18.75 mm；这不等于稳定持物期的两个压力中心始终错高。后续 50 ms 窗口两指均可在约 18.8 mm 高度跨度内产生承载点，完整点范围与冲量加权描述见 JSON。

记录到的机器人碰撞形状是 `/World/Franka/panda_leftfinger/geometry/panda_leftfinger` 与对应 rightfinger；杯体均为 `/World/Cuvette/Collision/band1_cell00/02/10/12/20/22` 中的壁身凸包。闭合配置中这些输入形状 z 范围相同：5.163099–67.220905 mm；未见初次或选定持物窗口切换到底部形状或顶部 `band2`。这些是输入 convexHull bounds 和实际回调 prim，不能据此宣称已独立检查 PhysX cooked geometry。

## 路点核对与因果边界

grasp03 原始 action8 抵达 0.826 m 后，action9 到约 0.801 m、action10 到 0.796 m，action11 才执行 3 s 闭爪（logical 9 mm / 每指上限 5 N）。因此该记录可作为同名义抓取高度的对照；它与 teacher02 仍有闭合保持逻辑、姿态反馈、时序及 5/8 N 驱动上限差异，不能将差异单归于某一项。GPT01 更低约 3.14 mm 仍抓持稳定，也不支持“较低抓点必然滑脱”。

teacher02 的初始错高接触和来源底座支撑具备引起微小摇摆的条件，但本核对未证明其因果。既有 [teacher02 漂移审读](../teacher_camera_v2_02_grasp_slip_analysis/README.md) 已将 608.994 µm 杯底参考漂移拆解为姿态杆臂与较小锚点位移；仍保留原始 GRASP_SLIP。grasp03 原始抓持最大相对位置漂移 2.698 µm，GPT01 为 1.778 µm；它们是模拟器内部诊断量，不能称硬件精度，且两条均未完成完整装载。

## 来源与范围

[summary.json](summary.json) 包含四个窗口（首承载接触、scorer reference 后 50 ms、lift 前 100 ms、source clear 后 50 ms）、每指实际点范围、hand/cup/world 坐标、真实 pair prim、配置输入 bounds、源 SHA256 与路点回执摘录。所有结果/评分/配置 SHA 均再次匹配各自已闭合归档的保护清单；gzip 原始日志整流解压 SHA 已在各闭合审计验证。本次只读选定前缀并核对归档 gzip SHA，不重复声称做了一次全流解压。

这些碰撞 prim 与世界坐标仅用于有权限的离线诊断，未送入 policy；不改变历史 H5、原始标签、评分参考点或阈值。
