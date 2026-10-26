# 已关闭状态：仅用于相机重建渲染

2026-10-27。两个 JSON 使用 `labsim.Project_v1_1.render_reconstruction_states.v1`，包含真实 9 维关节位置、杯体世界 pose、状态时间与来源 SHA。所有值来自已关闭记录，未猜测杯体位置；原数据、标签、相机或控制代码均未改变。

[gpt03_states.json](gpt03_states.json) 包含 GPT03 初始 0.016667 s、闭爪后 14.016667 s、decision000014 动作前 28.016667 s。逐状态 raw 字典与 H5 `privileged/state_json` 完全一致，真实 q9 与 H5/public observation 三方一致。当前 H5 和 raw gzip 的完整 SHA 与闭合审计一致。此轮最终原始结论为 `SAFETY_COLLISION`、task/grasp false，不能因早期状态可重建而改写。

[teacher02_visual_comparison_states.json](teacher02_visual_comparison_states.json) 包含历史 teacher02 的 INSERT 首命令前 74.85 s 与 OPEN 首命令前 110.616667 s。时间来自实际 phase-transition 事件，与 H5 observation timestamp 对齐；状态 phase 可能仍记前一阶段。该源为较早的 `4d19b6c` 运行，完整走过教师阶段但最终仍 `GRASP_SLIP / task_success=false`，仅用作插入及开爪视野对照，不能计为当前教师回归通过。

允许用途仅为在独立重建中设置记录的 articulation positions 和杯体世界 pose，生成新候选机位的静态 render QA。新图不是原始模型输入，不证明新动作或新轨迹执行，不构成新 episode；不送模型、不用于控制、不做 GT crop。物体 pose 保持原 vessel object/bottom frame 约定，不能当成 COM。关节按原 articulation 的前七轴与末两指顺序复现，不能猜 USD 名称。保留原状态与 sensor 时钟区分，静态重建不证明原像素严格同时刻。
