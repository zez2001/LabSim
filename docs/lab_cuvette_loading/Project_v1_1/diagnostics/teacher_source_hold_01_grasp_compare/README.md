# Teacher GRASP 姿态保持对照（2026-10-27）

关闭 GRASP 锁存后的杯姿态反馈后，该段最大杯底相对漂移从 teacher02 的 **608.994 µm** 降到 source_hold01 的 **0.891 µm**。但 source_hold01 在 **EXTRACT 起始 45.833 ms 后**仍发生 **272.280 µm** 越界，全局最大 **274.017 µm / 0.317358°**，原始任务结局仍为 **false / GRASP_SLIP**。未改阈值、评分参考、原始数据或标签。

| 对照 | teacher_camera_v2_02 | teacher_source_hold_01 |
|---|---:|---:|
| 实际运行提交 | `4d19b6ca` | `590f3462` |
| scorer 参考 / 双侧连续接触 | 18.145833 s | 18.145833 s |
| GRASP 段最大杯底漂移 | 608.994 µm，18.245833 s | 0.891 µm，18.312500 s |
| 首次超过 200 µm | 18.191667 s，GRASP | 18.962500 s，EXTRACT |
| 全流程抓持门控最大杯底漂移 | 608.994 µm，GRASP | 274.017 µm，24.804167 s EXTRACT |
| 最大相对姿态变化 | 0.705896° | 0.317358° |
| 53 mm 分析锚点最大漂移 | 64.096 µm | 31.615 µm |
| 原始完整任务 / BC资格 | false / false | false / false |

![真实早期轨迹](early_grasp_extract.png)

图中虚线为既有 200 µm 判据；点线是分析锚点，不能替换杯底验收量。17.95–19.4 s 曲线来自原始 gzip 物理日志，未插值。两条曲线都相对各自原 scorer 的 18.145833 s 参考；参考形成前的图段仅用于上下文，不能另算成功窗口。每指力为实际 tensor normal force，上限 8 N 是驱动配置，不是实测接触力。

## 首次越界发生在来源支撑尚未消失时

source_hold01 的 teacher EXTRACT 在 18.916667 s 开始，首次越界为 18.962500 s，早于独立 `actual_lift_started`（杯底抬升超过 1 mm，19.320833 s）约 0.358333 s。此刻 TCP z=0.796004 m、杯底来源间隙 −1.241 µm、environment 向上净力约 0.291 N，双指仍有 0.262 / 0.162 N。不能把这一事件称为已经离架后的杯体滑脱。

相对 scorer 参考，杯世界姿态改变约 0.314967°，实际 TCP 姿态仅改变 0.000572°、command FK TCP 约 0.000257°。对应杯底相对漂移为 272.280 µm，但 53 mm 锚点漂移为 29.158 µm、锚点轴向约 19.873 µm、姿态杆臂项为 291.207 µm。因此这一数值主要含杯体摇摆的杆臂效应，不能叫 272 µm 纯轴滑；也不能用锚点较小来抹掉原始杯底 200 µm 门槛。

全局峰发生在已离架的 24.804167 s：底部漂移 274.017 µm、双指 0.964 / 0.942 N、environment 力 0。这里是早期形成偏移的最大值，不表示此刻才首次失稳。独立物理分段 extraction 的局部重新参考漂移仅 1.748 µm；该分析分段从实际抬升开始，未包含前面的越界，不能拿它替换原始持续抓持参考。

## 配置、接触与结论边界

两份已闭合 config 逐字段比较，仅 `experiment.controller_version` 和 `teacher_execution.version` 从 v1 改为 v2；资产、物理、相机、验收、抓取高度、力上限及 retimer 均相同。实际提交与 frozen SHA 不同，均保留。提交范围还包含独立 joint API 语义修复，不能宣称整个提交只改了一个源代码点；本 teacher 对照意图为新 controller 仅抑制 GRASP 锁存后姿态纠正。

source_hold01 的首左右接触时刻/点与 teacher02 完全一致：右指 18.020833 s、杯局部 z约39.880 mm；左指 18.041667 s、z约58.628 mm。均同 `band1` 壁身形状，实际 TCP 约0.796 m。具体回调 prim、cup/hand/world 点范围及来源 SHA 见 [contact_evidence.json](contact_evidence.json)。其他已闭合 generic/GPT 对照见 [接触高度核对](../contact_height_compare_20261027/README.md)；generic03 的0.826 m是接近路点，实际闭爪同为0.796 m。

这对运行支持“GRASP 姿态反馈导致先前 GRASP 峰值的贡献已消除”的有限结论，也暴露 EXTRACT 起步时仍存在杯体姿态松弛/摇摆。它没有证明具体摩擦/接触成因。后续可用原阈值评估通用、仅接触信号驱动的近接触慢闭合与持物逻辑；不得重置 score 参考、放宽 200 µm 或 pose jump 阈值来隐藏失败。尚未运行的新控制变体不计入本结论。

## 闭合、可读与无损归档

PID122401 已消失，supervisor 的真实 `Popen.wait` 退出码0，墙钟1048.889 s。全124.266667 s / 7455转换 / 40个独立H5 dataset 均分块完整读取；H5、result、meta、collector labels、原 independent score snapshot 和时间/观测序列一致。teacher原生控制没有 public action receipt，未虚构回执。183个原始非raw文件 SHA 全部不变；两raw日志1,760,909,104→246,778,241 B，完整解压字节与 SHA 相等，释放1,514,130,863 B。详见 [闭合读审计](../teacher_source_hold_01_closed_read_archive.json)。

record_valid / record_integrity_valid / physics_trustworthy 均为 true，success_bc_eligible 为 false。完整流程动作已执行且后段稳定，仍不等于独立任务成功。坐标/接触仅限离线有权限诊断，未输入 policy；无新增 GPU/API 运行，无训练、真实校准或硬件精度结论。

[完整复算](summary.json) 保留29825条物理记录的流式 SHA、5项原评分最大值复现、各阶段峰值与实际事件；[紧凑证据](evidence.json) 汇总配置差异、SHA和关键时刻；[曲线CSV](early_grasp_extract.csv) 用于独立重画。
