# Teacher 慢闭合后保持力审读（2026-10-27）

结论：slow_close01 改善闭合冲击后，GRASP→EXTRACT 时实际保持力不足以维持既有2倍重力裕量；即使瞬时名义摩擦上界跌至重力的0.351倍，两指仍都超过0.03 N接触阈值，generic helper一直 confirmed / hold_contact_target。teacher与generic将同一10.418463 mm开口冻结，未随实测指位变化而继续收紧。本证据支持修复仅使用机器人指位/力的保持反馈；尚不能宣称某个修复已在物理运行通过。

原始结局：19.966667 s / 1197转换，**false / GRASP_SLIP（task域）**；record_valid、integrity、physics可信均true，BCfalse。40个H5 dataset全读、标签/时间对齐通过；正常failure ACT/DP批读取通过、success拒绝。原阈值、标签、配置、模型和运行代码未改。

## 既有假设与实际法向力

质量20 g，mg=0.1962 N；既有teacher/helper采用的名义组合动态摩擦系数为sqrt(0.5×0.8)=0.632456。若两指均分载荷，仅抵重力需每指0.155110 N；按已有 safety factor=2，目标为每指0.310219 N，对应kp=2000 N/m的名义压缩155.110 µm/指。每指8 N仅是驱动上限，未在此次实际0.05–0.4 N法向力区间生效为恒力目标。

| 对照窗口（按各自EXTRACT对齐） | teacher02 | source_hold01 | slow_close01 |
|---|---:|---:|---:|
| GRASP最后300 ms，左/右力中位 | .947/.947 N | .761/1.341 N | .207/.389 N |
| 同窗口muΣN/mg中位 | 6.106 | 6.774 | 1.920 |
| EXTRACT后100–400 ms，左/右中位 | .947/.947 N | .949/.948 N | .202/.202 N |
| 同窗口muΣN/mg中位 | 6.105 | 6.117 | 1.302 |
| EXTRACT前100 ms最小muΣN/mg | 6.090 | 1.367 | **0.351** |
| 应用总开口 | 9.666667 mm | 9.666667 mm | **10.418463 mm** |

上述muΣN是名义库仑模型容量上界，不是实测竖向摩擦，也不证明实际PhysX有效系数或真实硬件承载能力。balanced单指目标与总容量条件分别列出，不能用某一弱指直接断言全部负载分配。三条轨迹不是完整任务成功率比较，前两条也均保留原GRASP_SLIP。

![真实力、开口与相对运动](force_opening_phase_comparison.png)

图按各自真实EXTRACT切换时刻对齐，原始240 Hz采样、未插值。v3 EXTRACT切换=19.483333 s；teacher02/source_hold=18.916667 s。锚点轴向量仅分析，不替换原杯底验收量。

## 明确的时序与双层冻结

18.633333 s首次双侧接触时，实测总开口10.728683 mm；teacher候选=measured−2×155.110 µm=10.418463 mm，teacher与generic同tick冻结此值。18.733333 s连续0.1 s后确认接触。末300 ms实际力中位.207/.389 N，所有72个物理样本的名义总容量都略低于既有2倍裕量；“confirmed”仅证明接触持续，不证明承载裕量达到要求。

19.483333 s开始EXTRACT。前100 ms中6/24个物理采样的名义容量甚至低于mg，但全部24/24样本的两指仍>.03 N，所以基于contact loss的恢复分支不会触发。低于mg的样本组为19.525000 s单点、19.537500–19.541667 s两点、19.550000–19.558333 s三点；这些是离散采样跨度，不能假定两点之间力始终不变。

19.554167 s首次越200 µm时，双指.050191/.058685 N、容量比.350965，杯仍在来源底座支撑（底隙−.955 µm、environment竖直约.151 N）。末态手TCP升至.797776 m、杯底只到.743262 m；杯底相对漂移1.591964 mm，其中配置锚点轴向约1.500046 mm。它与先前sourcehold约274 µm主要姿态杆臂的现象不同，本轮主要出现真实轴向相对滑移。独立actual_lift_started（>1mm）与source clear事件均未发生。

末态实测总开口10.620899 mm，应用仍10.418463 mm，等效每指指位差仅101.218 µm，kp估算约.202 N，与实测.201/.201 N相符。按同一既有压缩假设重算候选为10.310680 mm，比冻结目标还需闭合约107.784 µm总量；generic已计算该候选却未应用。trace从参考前200 ms至结束仅original_ramp、first_bilateral_freeze、hold_contact_target，无contact_loss_slow_close。

teacher将冻结值当每tick动作opening传出，直接teacher env.step没有原始raw_model_action目标，task又以该opening作为generic logical。现有generic在双侧>.03且已有freeze时只保持旧目标；即便触发失触恢复，logical=previous=frozen时min(previous,max(logical,previous−vdt))仍等于previous。因此这两层状态既缺少“接触仍在但保持力不足”的反馈，也可能阻断后续进一步闭合。

固定执行源码的独立只读复核见 [双层保持机制审查](../teacher_slow_close_01_hold_mechanism_review/README.md)，保留7份c793源码SHA与带行号摘录；它与本轮真实力/开口时序相互印证，仍不替代新修复的物理验证。

## 可实施边界与闭合证明

可在新版本helper中以机器人指位与法向力持续检查既有mg/mu/safety要求，并对开口做有速率界的单向收紧；明确区分显式开指意图、原始闭合逻辑目标与一次冻结后的应用目标。应维持既有8 N上限、kp、摩擦、压缩边界与评分阈值；不能依赖杯真值或teacher阶段来调力，也不能只把接触确认延长当作保持力证明。具体实现与新物理验证由root负责，本审读未修改runtime。

PID229751已消失，真实Popen.wait exit0，进程墙钟194.663 s；执行提交c793a12b8f097eb47a9158a708d896993a05116c。95个原始非raw文件SHA全未变，两raw日志251,995,993→33,683,582 B，整流解压SHA/bytes相等，释放218,312,411 B。原score中的pending integrity快照保留，collector最终资格与独立全H5读校验区分。

[完整三run数值](summary.json) · [紧凑证据](evidence.json) · [240 Hz力/开口CSV](physics_force_opening.csv) · [60 Hz两层分派CSV](control_dispatch.csv) · [闭合全读审计](../teacher_slow_close_01_closed_read_archive.json) · [正常reader](../../validation/teacher_slow_close_01_normal_reader.json)

仅CPU离线分析；无API/GPU、训练、旧结果改写或硬件精度结论。cup坐标只用于有权限的事后诊断，未输入policy。postretreat未发生，保持原unavailable/null。
