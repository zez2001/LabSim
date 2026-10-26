# baseline-close01：真实支撑存在，但支撑与精对准未并发

2026-10-27，纯 CPU 对已闭合 `teacher_baseline_close_01`、历史 `teacher_camera_v2_02` 和 `teacher_source_hold_01` 的全部物理 JSONL 流式复核。三份解压 SHA/长度均匹配归档前，原分数、标签和阈值不改。详细样本、原始事件和来源 SHA 见 [summary.json](summary.json)。

baseline01 的 `loading_candidate_sequence_observed / release_observed / retreat_observed / stable_after_retreat` 均 true，但 `loading_sequence_observed=false`。required events 中唯一缺项是 **`correct_target_supported`**，连 `loaded_supported_candidate` 也没有发生。原 scorer 要求同一物理样本的目标平面 XY≤100 µm、tilt≤0.15°、yaw≤0.2°、深度与底间距到位、分类底部支撑≥0.1 N，且器皿位于所选目标内。全 raw 中满足该组合的样本数为零，与原事件缺失一致；这里不先断言判分 bug。

107.608333 s 杯首先满足精对准和几何到位，底力仍为 0。teacher 于 107.616667 s 明确以 `support_not_yet_claimed=true` 进入支持卸载探测。**实际底部支撑首次形成于 110.145833 s**：0.238589 N、gap −0.376 µm、contains=true，但此时 XY=188.527 µm、tilt=0.200089°，未同时通过精对准门槛。

在 OPEN 阶段转换前已经有 **113 个连续 supported+inside 物理样本，约 0.470833 s**，不是 force=0 直接张开。110.616667 s 切换 OPEN 的真实状态为 floor=0.190608 N、gap=−0.179 µm、tilt=0.004304°、yaw=−0.018372°、contains=true，**唯 XY=187.961 µm 超过 100 µm**。所有 supported 样本中，最接近完整精对准的 XY 仍为 186.969 µm，不能用最终器皿平稳或在座内替代此项。

首次满足独立脱指条件的真实样本在 **110.729167 s，已进入 OPEN**：双指 q≈6.0078/6.0079 mm，超过每指 6 mm 的原判据，双侧接触力均为 0；持续后于 110.783333 s 记录 `both_fingers_open_and_detached`。这不是把卸载时向内回收的指位误计为开爪。teacher 的 phase-transition instant、该区间分派的命令与物理后继状态分开解释，原事件时刻均保留。

teacher `_supported` 只检查 force、gap、tilt≤1°等支撑条件；SUPPORT_TRANSFER 期间没有 XY feedback，OPEN 条件为该支撑与位置安静窗口。原 scorer 还要求前述更紧的并发 alignment。支撑后杯实际目标平面位置偏离，足以解释 `TASK_INCOMPLETE`，不是没有任何真实支撑。底力约 0.1962 N 对应当前配置质量重力，不构成硬件接触力标定。

![支持、精对准和开爪时序](support_alignment_and_opening.png)

历史两轮也存在相同缺项。teacher02 在 OPEN 前有 179 个 supported+inside 样本，OPEN 时 XY=169.516 µm，最佳 supported alignment 的 XY 仍为 168.591 µm；source-hold01 对应 184 个样本，OPEN 时 XY=212.948 µm，最佳仍为 212.827 µm。两轮原分数均 `GRASP_SLIP`，同时记录 candidate/release/retreat/post-retreat stable=true、完整 loading_sequence=false；较高优先级的抓持失败曾掩盖了这个额外的流程缺项。原历史标签不回填或改写。

可实施建议是 teacher 在支撑形成之后、OPEN 之前再核对原 alignment；未达标应保留失败/停止，而非放宽门槛。是否用同样材料、力上限和有界动作维持/重建支撑后对准，需要独立运行验证；本审计不预设完整物理根因或修复有效。物体真值和接触信息只用于闭合后的诊断，不送 GPT，不用于 GT crop 或公共策略控制。

撤离后原完整 3 s/721 样本稳定判据为 true，测得位置漂移约 0.108482 µm、朝向变化 0.000216219°；这些不是实物精度，也不能覆盖缺失的支撑精对准事件。原 false/TASK_INCOMPLETE、valid/integrity/physics true、BC false 均保留。
