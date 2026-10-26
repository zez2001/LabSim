# EXTRACT冻结XY单因素：已闭合失败（2026-10-27）

冻结EXTRACT名义XY后，仍在**同一19.533333 s（EXTRACT+50 ms）**越过原200 µm杯底相对漂移门槛，最终**taskfalse / GRASP_SLIP**。这否定“冻结XY这一个改变足以让该固定场景通过”的假设；它不证明XY完全没有贡献，也不推广到其他抓取条件。

| 原始独立结果 | preload01（9e48016） | lateral_hold01（109e637） |
|---|---:|---:|
| 首次200 µm越界 | 19.533333 s /247.490 µm | 19.533333 s /242.147 µm |
| 全局body-bottom最大漂移 | 1.547611 mm | 1.520247 mm |
| 全局相对姿态最大变化 | 1.751228° | 1.752554° |
| 配置锚点最大漂移 / 轴向 | 246.290 /230.771 µm | 248.516 /221.138 µm |
| 原始完整任务 /BC | false /false | false /false |

本轮EXTRACT nominal target XY全程逐值不变（max delta=0），requested quaternion仍固定。physics/vessel/robot/gripper/acceptance/cameras/robot_tracking七组配置逐字段相等，保存配置仅两处controller版本标签不同，XY抑制位于v4 controller实现；三份scorer源码逐字节不变，详情见[evidence.json](evidence.json)。新helper实际预载5 tick、释放slew0 tick；全部观察到的预载步长和总反馈预算在原声明界内，释放未执行不声称验证。

首次越界时，杯世界转约.331035°，actual hand仅.000891°、command FK约.000097°；杯底仍有来源支撑（source gap+.454 µm、environment竖直约.267 N）。即便nominal XY不动，杯转与手转仍明显分离，支持继续排查来源支撑转换/指接触重分布和初始姿态，不能把初始摇摆归为必需的truth XY修正。较大的env向上力也不等于杯已离开；独立actual lift超过1 mm在19.920833 s才发生，source clear未发生。

运行20.066667 s /1203转换，真实process exit0、PID395840已消失，wall184.570 s。40个H5独立dataset全读通过，时间/标签/动作/原评分快照一致；normal failure ACT/DP读取通过、success拒绝，H5无external link/外部dataset或VDS依赖。95个原始nonraw SHA未变；两raw252,496,704→33,830,927 B，全解压SHA/bytes一致，省218,665,777 B。原record/integrity/physics均true，postretreat unavailable/stable null，均不改。

[完整姿态/物理前缀与CSV](summary.json) · [紧凑A/B/config证据](evidence.json) · [实际helper分支/全5项评分复算](../teacher_lateral_hold_01_preload_audit/summary.json) · [闭合H5/归档](../teacher_lateral_hold_01_closed_read_archive.json) · [正常reader](../../validation/teacher_lateral_hold_01_normal_reader.json) · [此前因果时序及grasp04起算边界](../teacher_preload_01_causal_timing_review/README.md)

仅CPU只读审读，无API/GPU、runtime/物理/阈值/原始标签改动，不作真实精度或正式成功率结论。GPT03是另一个独立标准reset调试，不能据其后续结果改写本teacher失败。
