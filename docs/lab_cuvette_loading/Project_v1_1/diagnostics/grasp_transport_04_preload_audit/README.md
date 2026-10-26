# Contact hold v2：grasp04 已闭合回归（2026-10-27）

真实结果：33.15 s / 1988转换 / 17条公共动作回执，抓持与离架通过；原完整任务仍false / POLICY_BUDGET（CONTROL_DIAGNOSTIC_COMPLETE），transport_success=false、BCfalse。该固定前缀短搬运诊断不是完整装载成功。

新helper v2的实际分支计数：original_ramp1267 tick、first_bilateral_freeze1 tick、hold_contact_target720 tick；**measured-force preload adjustment=0，release slew=0**。确认接触后的最弱单指样本仍≥1.206464 N，高于既有0.310219 N/指保持目标，因此此次正常回归未需要新预载；固定动作没有释放，不能用它宣称新释放分支已验证。

原body-bottom相对最大漂移2.698423 µm、姿态.015755°、配置53 mm锚点1.771342 µm、轴向.847628 µm、横向1.766937 µm。五项均从全7957条物理行按原scorer门控复算，且与closed grasp03五项保存值逐项完全相等。这里的微米量是模拟器相对状态诊断，不是硬件精度，也不是全任务成功率。

完整H5的40个独立dataset分块全读、标签/动作/时间/后继对齐通过；H5无external link、外部dataset存储或外部VDS来源。正常full-loading reader的success与failure入口都按control_diagnostic资格拒绝，保留原eligible_for_failure_analysis=true作为分析资格，不将诊断样例当正常训练数据。

PID379613已消失，规范run_directory退出证明：实际exit0、wall283.546 s、执行9e48016412907385d1a8c9e40860139f3d730764。65个原始非raw SHA未变，两raw435,404,280→61,981,329 B，完整解压SHA/bytes一致，释放373,422,951 B。原H5、score、labels、视频、proof未改。postretreat原unavailable/stable null保持。

[分支/指标JSON](summary.json) · [1988 tick分派CSV](control_trace.csv) · [全H5闭合审计](../grasp_transport_04_closed_read_archive.json) · [正常reader与H5外部依赖检查](../../validation/grasp_transport_04_normal_reader.json)

新teacher_preload01仍另等独立关闭后的真实评分，不能把grasp04诊断的通过当teacher或GPT通过。此审读仅CPU，无API/GPU、代码或阈值修改。
