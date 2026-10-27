# 本轮已关闭实验的阅读媒体

本页先前的三条主片清单保持原范围；后续新增的 GPT06、GPT07 及同次 teacher 成功局部见下方“新增闭合媒体”。各自独立回执是对应媒体的依据，不把较早总清单扩写成覆盖全部后续运行。

默认阅读入口是以下三条**同一次运行的完整连续视频**，合计 10,975,379 字节（约 10.98 MB）。它们是原生 `dual_view.mp4` 的 H.264 CRF23 有损阅读派生版，保留全部源帧、顺序、分辨率及 PTS（核对容差 1.1 µs）；没有截取、拼接、变速、增添标注或改写状态。派生像素不与原视频逐字节相同，也不构成新实验。

- [teacher v7 首条完整成功](reading/teacher_support_align_01_full.mp4)：`teacher_support_align_01`，实际 runtime `0b922ec`；3771 帧，视频约 125.7 秒、实际仿真结束于 125.666667 秒。原独立 `task_success / record_valid / record_integrity_valid / physics_trustworthy / success_bc_eligible` 均为 true。该条是固定场景五条闭合成功的代表；其余重复不重复复制视频。[阅读派生回执](reading/teacher_support_align_01_full_reading_receipt.json)；[原主片来源及关闭证明](teacher_support_align_01_full_media_receipt.json)。
- [GPT04 座口受阻完整失败](reading/gpt_debug_04_rim_obstruction_full.mp4)：实际 runtime `63410bf`、prompt v4，3442 帧，视频约 114.733 秒、实际仿真结束于 114.716667 秒。原结果为 `false / GRASP_SLIP`，模型最后主动 finish，没有独立合格的释放、撤离；post-retreat 为 unavailable / stable null。[阅读派生回执](reading/gpt_debug_04_rim_obstruction_full_reading_receipt.json)；[原主片来源回执](gpt_debug_04_rim_obstruction_full_media_receipt.json)。
- [GPT05 末端臂段碰盖完整失败](reading/gpt_debug_05_link6_collision_full.mp4)：实际 runtime `58da857`、P6 temporal，1498 帧，视频约 49.933 秒、实际仿真结束于 49.916667 秒。原结果为 `false / SAFETY_COLLISION`，有效物理中的 `panda_link6` 与 `SourceMesh5` 接触触发安全停机；不是执行器/IK 故障，未到入口、未验证 P6 的 100 µm 停看策略，也未释放、撤离。[阅读派生回执](reading/gpt_debug_05_link6_collision_full_reading_receipt.json)；[闭合碰撞审计](../diagnostics/gpt_debug_05_collision_audit/README.md)。

[阅读派生总清单](reading/reading_index.json) 保存原/派生 SHA256、原生媒体回执、完整逐帧仿真时间与 PTS 检查、编码命令和实际视觉 QA 范围。三条均已 CPU 全解码通过，并实际检查各自关键帧；没有新 GPU、API 或原运行修改。原视频及其闭合来源仍可按回执追溯，不要求小阅读包重复携带较大的原生 MP4 或 H5/raw。严格同时曝光、实物标定、全局 cooked 几何精度及真实接触力均未由媒体认证。

teacher 的正确支撑、开爪脱离、撤离及三秒稳定来自独立判分和闭合物理记录，不能用阶段字幕或最后一帧替代。其 VERIFY 末段腕视存在左侧裁切，侧视目标较小且有遮挡；GPT04 腕视可见杯/手相对移动，但不能直接确认座底支撑；GPT05 两个视角不能认证整个末端臂段的三维净空。

## 保留的较早对照附件

- [GPT03 原完整失败主片](gpt_debug_03_collision_full.mp4)：原 `dual_view.mp4` 字节复制，891 帧 / 29.700 秒视频，实际仿真 29.666667 秒；runtime `109e637`，原 `false / SAFETY_COLLISION`，不是 P7 或 GPT06 结果。
- [teacher v6 支撑释放双视局部](teacher_baseline_close_01_support_release_dual_clip.mp4)及[同窗腕部近景](teacher_baseline_close_01_support_release_wrist_clip.mp4)：仅同一次 `teacher_baseline_close_01` 的局部片段，原 `false / TASK_INCOMPLETE` 保留。视频含 `LOCAL CLIP` 和原失败标注，不是完整成功。选窗 `[3210,3729)` 共 519 帧 / 17.300 秒，对应实际仿真 107.016667–124.266667 秒。原 OPEN 时 XY 187.961 µm 超过原 100 µm，缺独立 `correct_target_supported`；退让后三秒稳定不补足该缺门。

[较早媒体清单](media_manifest.json) 只覆盖其原有 GPT03 / v6 局部附件，保持原快照；新增完整主片与 reading 派生各用独立回执。P7 离线固定 ROI 预览不是模型实发输入，后续真实模型输入与任务成绩另按各次闭合证据读取。

## 新增闭合媒体

- [GPT06 主动结束完整阅读主片](reading/gpt_debug_06_safe_finish_full.mp4)：同一次 `9a4713c` / P7 运行，1081 帧，实际仿真终点 36.016667 秒；17 个模型决策、18 次网络请求、16 个物理动作加 finish。原 `false / TASK_INCOMPLETE / POLICY_FINISH_REQUEST`，已抓持和离架，未完成搬运、插入、释放、撤离。[独立阅读回执](reading/gpt_debug_06_safe_finish_full_reading_receipt.json)。
- [GPT07 主动观察完整阅读主片](reading/gpt_debug_07_active_view_incomplete_full.mp4)：同一次 `4226419` / P8 运行，2701 帧、3,462,674 字节，实际仿真终点 90.016667 秒；46 模型决策/网络请求、45 个物理动作加 finish。实际抓持、离架与持物搬运通过，模型因下降净空、插入深度和承托不确定主动结束；原 `false / TASK_INCOMPLETE`，没有合格释放、撤离或装载成功。[独立阅读回执](reading/gpt_debug_07_active_view_incomplete_full_reading_receipt.json)。
- [同次 teacher 成功释放撤离腕部局部](reading/teacher_support_align_01_release_wrist_clip.mp4)：**LOCAL CLIP，不是全程**。来自首条 `teacher_support_align_01` / `0b922ec` 完整成功原生腕部视频，源帧 `[3240,3771)` 共 531 帧、585,269 字节，对应实际仿真 **108.016667–125.666667 秒**。连续保留所选帧、分辨率与顺序，仅将 PTS 起点移至零，H.264 有损编码，无拼接或新增叠加标注。已完整解码，并实际查看双指张开脱离与撤离事件帧；不是新 native/GPT 运行，也不是用局部片段代替独立成功。[局部回执和选窗](reading/teacher_support_align_01_release_wrist_clip.receipt.json)。

两条新增 GPT 主片均完整保留全部帧和 PTS，已 CPU 全解码及实际关键帧视觉 QA；其 post-retreat 仍为 unavailable / stable null。此段截止时尚无 P9 结果；最新 P9/GPT08 主片见下节，原未完成标签保留。旧回执、原 native 视频与标签未改。

## 最新 GPT08 完整阅读主片

[完整阅读录像](reading/gpt_debug_08_self_state_incomplete_full.mp4)为同一次实际 P9/GPT08 的全帧 H264 派生，1954帧/2,547,678字节；来源SHA、PTS、完整CPU解码与实际关键帧QA见[独立回执](reading/gpt_debug_08_self_state_incomplete_full_reading_receipt.json)。不裁时、不拼接、不变速，保留原分辨率；有损派生不保证逐像素等同native。

原判分为TASK_INCOMPLETE/POLICY_FINISH_REQUEST，34决策/34网络请求、33物理动作加finish，终点65.116667秒；抓持、离架和搬运已发生，三次100µm下降请求已执行，未建立合格入座、支撑、释放与撤离。未到阶段的模型图仍为unavailable，teacher成功局部不能替代GPT输入。完整失败主片不是任务成功，也不证明安全整路线。没有更改既有回执。
