# Stage5 到最终报告的最小输入更新审查

结论：现有 `generate_report.py` 已支持最终 cohort、单值 JSON pointer、相对媒体链接和宽图；无需扩展生成器。保留 stage5 快照，以新输入文件完成最后的实体 SHA 与正文更新，再由 root 执行首次 marker、author 和逐页渲染。此审查没有 author、marker、DOCX 或 GPU/API。

## 教师 cohort 与正文必须同步

生成器的 `cohorts` 只用于校验和 `report_build.json`，不会自动改写正文或生成结果表。仅把 teacher 的 `completed_count` 改成 5，会留下首页、第三组和末组仍写“首条/其余待计”的陈旧文字。

等五条实际证明、PID 消失和全 H5/正常 reader 审计完成后，把自动生成的 `diagnostics/teacher_standard_v7_closed_data_cohort_01.json` 登记为 scope=teacher 的新来源。`completed_count` 是实际已关闭并审计的集数，不能当成成功数；成功数另用 `actual_qualified_full_success_count`。若提前停止，保留实际数和 incomplete，不能为 planned_count 补齐。

最小改动为：

- 将 teacher cohort 的 summary_source 指向最终 cohort，真实完成计划时才设 closed。
- 同步改 `metadata.conclusion`、第 1 组总览、第 3 组数据段、第 7 组发布状态及末尾 limitations。
- 现有首条事件表继续作代表；其后加一张短的五集读取表，或一段“五集逐一 ACT/DP 成功读取通过”加完整 cohort 链接。重复 2–5 不增加视频和逐步长表。
- 数值单元格可直接使用 JSON pointer，例如 `{"source":"teacher_v7_cohort","pointer":"/actual_closed_data_audits"}`；未发生窗口和未知任务结果保持 null。

新 v7 实际是五个独立 `--episodes 1` 原生进程（seed 0–4，首条 GUI，其余 headless），不能改写成已验证同进程 `--episodes 5`。固定场景、随机化关闭的重复只支撑确定性复现，不是泛化成功率。首条便携验收继续保留“自含 H5 / 正常 batch / 替代路径读取”与“未训练、非新机器部署”的范围。

## 内嵌图只改来源即可

第 4 组原 `support_ab_fig` 指向三栏图且 max_height_cm=5.3，缩小后不适合正文。最少只将该 source 的 path/sha256/bytes 指向新 `teacher_v6_v7_XY_report.png`，figure block 的 source ID 可不变；建议 max_height_cm 为 5.8–6.0。

新图为 1600×600、字号至少 14 pt，SHA256：`503fc06ef75053d99028b93aa159e79c17449b56e1844a5742b8bac8d2aab610`。新增 `XY_report_figure_receipt.json` 来源，其 SHA 为 `b2d5f39360fbfba6bceab6270bee78608c6f70347a4096890485916b0bb5388b`。caption 明确“仅 XY；倾角和支撑力见完整三栏图”。

另给原三栏图一个来源 ID 并放显式附件链接，原图、原来源清单和原 manifest 均保持。v7 中间实际振荡不能写成全阶段始终稳定；菱形是原独立支撑物理点，教师阶段仅用于横轴起点。生成器按宽高比与页正文宽度缩放，输入高度不是实际渲染可读性的保证，仍需逐页实看。

## GPT 与发布版本按实际新证据收口

stage5 的 GPT04 历史行、原 P4/63410bf 身份、51 决策/50 执行与 false GRASP_SLIP 保留。P5 只做过 CPU；旧 GPT05 等待队列在任何 native/API 前取消，不能记成模型尝试或失败。P6 的提示与 ≤100 µm 候选仍以实际公开输入 QA 和已关闭结果为准，不能把候选文本或 CPU 通过当作已实现检测。

新版已关闭 GPT05 出现后，更新第 5/6/7 组与 debug cohort，并明确其实际 prompt、profile、相机、源代码和共享账本截止点。已有 GPT04 指端线索只适合增加一句局限及链接：法向左右不对称可能可见，法向总和和失触不是本次早期可靠线索；更强摩擦变化未公开，原 raw 内点也不是历史模型收到的 API 观测。不能据此承诺 P6 可检测。

正式五次只有真实完整成功及 reader/输入 QA 门控后才能计入。未启动写 not_run；预算阻塞写 blocked_budget；不满五次保留全部真实尝试并写 incomplete。`completed_count`、成功、有效任务失败、执行/仿真无效与 task=null 分开，不能把 null 格式化成 false 或零。生成器的 JSON pointer 已保留 null 文义。

最终当前代码 CI 与实际运行版本分列：0b 教师组、历史 63410bf GPT04、后续 P6/GPT 与同源 teacher 各用原记录完整 commit。实际 source-equivalence 必须对比闭合运行的 `project_scene_contract.frozen_scene_sha256` 和独立 `geometry_audit_fingerprint` 两个字段；不能混用，也不能只由当前 HEAD 推断相同。

## 页数与精简包

保留现有 7 个逻辑页组即可，不增加进展专页；新增逐集汇总替换旧待办文字。代码段每行最多 90 字符是现有校验要求。最终渲染若超过 8 页，先删重复说明、缩短表格文本或将详细记录改链接，保留正文 11 pt、表格 9.5 pt 和可读图字。

每个最终 MP4 必须同时在 sources 和正文 links 声明；包计划不会自动变成正文链接。已选 teacher 首完整片和代表 GPT 完整片优先，后续重复教师不再复制。最终新 GPT 录像大小尚未知，应在实际 stat 后核 ≤80,000,000 B；如替换代表片，旧调试的原结论/小证据仍保留来源，不能留断链或把局部片段称为完整。

保持仓库相对层级以满足 DOCX 的原相对链接；打包工具不改写 DOCX。新增 XY、完整三栏附件、cohort、媒体回执及所有正文目标都需进入最终 allowlist。约 1.944 GB 的成功 H5 只保留出处、SHA 与读取证明，不因 JSON 内有绝对 provenance 字符串就声称已随包发布。最终检查也应覆盖所选 MD 的本地二级链接，明确哪些是包内证据、哪些只是源工程出处。

草稿阶段以 bundled Python 运行 `--allow-draft --validate-only`；确认实证和最终状态后设 finalized=true，再运行不带 allow-draft 的 `--validate-only`。这些只核存在/SHA/schema，不是排版或物理验证。第一次实际 DOCX create/edit 前由 root 执行 documents marker 恰好一次，之后 QA 重做不再 marker；本次审查未执行这些步骤。
