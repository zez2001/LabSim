# baseline-close01 保持分支与原评分复算

纯 CPU 读取已关闭记录。`summary.json` 对全 29825 条物理行解压字节做 SHA/长度核对，并复现原独立评分的杯底位置、朝向、anchor、anchor 轴向与横向五项最大值。原任务结果 false/TASK_INCOMPLETE 保留，grasp/transport true 不替代完整任务。

本轮实际 `first_bilateral_freeze` 一次、`hold_contact_target` 5374 次、普通 `explicit_opening_ramp` 317 次；额外测量力预载反馈 0 次、release-slew 0 次。不能据本次完整开爪声称未触发的 release-slew 分支被物理验证。force-hold v2 的参数与 8 N 上限均未改；测量接触力和驱动上限分开。

`control_trace.csv` 保存逐 tick 逻辑、分派、应用、实测开口与前后双指接触力。[闭合全读审计](../teacher_baseline_close_01_closed_read_archive.json) 保存原 H5/标签/视频/证明 SHA 保护和正常 reader 结果。[闭合 A/B](../teacher_baseline_close_01_ab_audit/README.md) 解释实际闭合模式和参考时序；[支持事件审计](../teacher_baseline_close_01_support_gate_audit/README.md) 解释总流程为何仍 false。无 GPU/API/训练，不改原记录。
