# 报告适配的 XY 单栏图

![教师 v6 与 v7 的实际 XY 误差及独立支撑点](teacher_v6_v7_XY_report.png)

该图为 1600×600 PNG，所有绘图文字的原始字号至少 14 pt，适合在报告内以约 5.3–6 cm 高度显示。橙色为原 `TASK_INCOMPLETE`，蓝色为原 `SUCCESS`；100 µm 门槛、两次实际 OPEN 转换、v7 原独立 `correct_target_supported` 点均保留。

原数据分别减去各自 SUPPORT 起点，保持独立原时间；没有插值、重采样或相同时长假设。单图只筛选原三栏图的 XY 栏，不把教师阶段当成成功证据。v7 过渡中的真实超门槛波动保留，完整成功还依赖 OPEN 同帧的支撑与姿态等原门槛及后续脱离、撤离和三秒稳定。

[独立来源与视觉验收回执](XY_report_figure_receipt.json) 保留四个输入实体 SHA256、脚本与复现命令。原 [三栏图](teacher_v6_v7_support_gate_comparison.png)、[原来源清单](figure_source_manifest.json) 和原 manifest 均未覆盖；倾角、底部支撑力、0.1962 N 重力参考仍可在[原说明](README.md)、三栏图、CSV 与摘要中复核。

本次只有已关闭记录的 CPU 绘图，没有读取活动集、GPU、API 或修改原数据/标签。
