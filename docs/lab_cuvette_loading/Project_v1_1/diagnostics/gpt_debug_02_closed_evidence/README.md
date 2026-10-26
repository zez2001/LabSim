# GPT02 已闭合真实安全失败（2026-10-27）

GPT02 真实执行 **33 次 API 决策 / 33 条接受动作 / 3591 转换 / 59.866667 s**，最终 **task_success=false，SAFETY_GEOMETRY_VIOLATION / INPUT_MATERIAL_PENETRATION**。record_valid、record_integrity_valid、physics_trustworthy 均 true；success BC false，正常 failure ACT/DP 批读取通过，success 过滤拒绝。它不是完整装载成功，也不是 GPT01 手体撞机身的相同故障。

## 实际链条与工具动作区分

在第一次杯—座实际接触之前，双指承载门控下的杯底相对参考漂移最大 **7.125 µm**；实际离架和累计水平搬运事件已发生。该有限前缀可描述为稳定抓持搬运，不能替换最终 grasp_success=false / transport_success=false。

**52.912500 s** 首次非零冲量杯—座接触：`/World/Cuvette/Collision/bottomn1n1` 对 `/World/Instrument/Collision/SourceMesh3`，世界接触点 z≈0.914000 m。原始 native callbacks 没有 forbidden robot-environment 事件；GPT01 则是 hand 对机身 `SourceMesh2`，首点 z≈0.915463 m。两者有相近世界高度，但参与形状、动作路径、时间和失败机制不同，不能称同一次碰撞复现。GPT02 先抬至 TCP≈1.113 m 再横向搬运，GPT01 在低处搬运时即停止。

**52.937500 s**，杯底停在入口、target-frame XY 误差 **2.602 mm**、target contains=false、底部支撑 **0 N**、底座间隙≈26.995 mm；座整体向上力约2.369 N是杯碰入口/顶面的反作用，不是腔底承托。这时仍是9 mm / 每指驱动上限4 N、尚未开爪，已首次越过200 µm抓持漂移门槛。模型继续下移，而杯底停在约0.914 m，手相对杯体下滑；55.008333 s原始双侧门控最大漂移已到 **16.956 mm**。不能将失败解释为开爪后才开始计算的伪滑移。

| 实际时刻 | 实际杯深度 | target-frame XY误差范数 | 腔底间隙 | 腔底支撑 | 原评分条件 |
|---|---:|---:|---:|---:|---|
| 52.016667 s | −8.961 mm | 2.597 mm | 35.961 mm | 0 N | 尚未进入 |
| 53.016667 s | 0.0069 mm | 2.603 mm | 26.993 mm | 0 N | contains=false |
| 55.016667 s，开始开爪 | 0.0020 mm | 2.618 mm | 26.998 mm | 0 N | contains=false；抓持早已越界 |
| 59.866667 s，安全停止 | 21.605 mm | 10.594 mm | 5.395 mm | 0 N | 倾斜114.920°；contains=false |

55.016667 s才请求11 mm/.5 N开爪，56.016667 s再请求40 mm；实际双指脱开。55.008333–57.020833 s native还记录了 hand 对杯顶部 `band2_cell10` 的接触；这属于杯与机器人接触，不是 forbidden robot-environment。后续机器人上移时杯体倾倒，最终输入材料重叠约 **0.385499 mm** 触发既有 safety guard。具体归因仍保留 scorer 的 `not_determined_by_scorer`；本时序不证明是唯一原因。

![实际杯停手移与接触轨迹](target_contact_release_curve.png)

图中TCP减初始抓持高度差仅提供上下文；它不是杯的实际位姿。红实线只表示原始双侧抓持门控，灰点线是门控外上下文（实际抓持attempt于56.2875 s结束），不把开爪后漂移计入原grasp指标。力轴在±2 N内线性、外部对数，保留终末碰撞峰，不将其压扁或裁掉。杯的真实材料最低点单独绘制。全程实际腔底支撑最大为 **0 N**。末态深度21.605 mm来自倾斜材料最低点，不能单凭一个正深度宣布插入成功。独立 loading candidate、loading sequence、release、retreat 事件均未满足；**stable_after_retreat=null，post_retreat status=unavailable / stable=null**。终末3 s不稳定。

## 数据、来源与归档

PID147063 已消失，supervisor真实 Popen.wait exit0，进程墙钟750.720 s；实际提交 `c793a12b8f097eb47a9158a708d896993a05116c`。40个独立 H5 dataset 全部分块完整读出；3591转换的时间/观测后继、33回执（最后51 ticks/0.85 s部分执行）、动作、原评分、meta和最终资格一致。所有 **174个原始非raw文件 SHA 未变**；两raw日志836,651,147→122,391,551 B，完整解压SHA与字节相等，释放714,259,596 B。H5、标签、原模型输入、视频和退出证明均未改。

[紧凑JSON](summary.json) · [几何/释放时间线](geometry_release_summary.json) · [实际 native pairs](native_positive_contacts.json) · [曲线CSV](target_contact_release_curve.csv) · [全读审计](../gpt_debug_02_closed_read_archive.json) · [正常 reader](../../validation/gpt_debug_02_normal_reader.json) · [全物理/任务摘录](../gpt_debug_02_contact_task_offline.json)

33次公开观测JSON、66张实际发给模型的JPEG、原manifest、记录的静态prompt/tool schema、公开toolcall/receipt、controller和trace由同轮 [perception证据](../gpt_debug_02_perception/README.md) 保存并独立按trace SHA核对；本审计又将其138项原始来源SHA与归档前174项保护清单交叉核对，所有原gpt_control文件均已保存、全部复制文件SHA/bytes一致，见 [wire交叉审计](wire_inputs_cross_audit.json)。本目录内座/杯/接触坐标为有权限的离线诊断，未送入policy。没有新增API/GPU、训练、阈值改动、真实精度或随机泛化结论。

保存范围不包含完整HTTP body或完整memory response item组；后者可能有未记录的私有reasoning项，因此不能称为保存全部原始请求。观察证据的原始字节和138项源SHA均未变。
