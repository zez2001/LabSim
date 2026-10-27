# LabSim Project v1 1 当前结果阅读说明 草稿

本文件与清单仅为打包计划，尚未生成桌面包。最终报告、GPT07闭合结果及最终预算待补，当前不得把本稿当作最终交付。打包时间 {{GENERATED_AT}}，实际提交 {{SOURCE_COMMIT}}，分支 {{BRANCH}}；完整工程 {{REPOSITORY_URL}}。交付SHA由最终打包清单产生，不预填未来提交。

先读最终[中文报告 DOCX](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.docx)或[Markdown](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.md)，再看[逐条结果表](docs/agent_handoff/Project_v1_1_current/current_results.stage8.draft.csv)和[提交与CI范围](docs/agent_handoff/Project_v1_1_current/version_scope.stage8.draft.json)。最终作者须把本说明中的“草稿”和未来占位更新为实际闭合结论。

当前实际结果是：原计划teacher五个独立进程在固定standard场景均完整成功；另58da和9a各一次教师回归成功，单列而不称7/5。GPT01–06为六个不同调试条件，均失败、0完整成功；GPT05实际25请求/P6，在搬运阶段碰盖，未进入100µm下降策略；GPT06实际17模型决策/18网络请求、P7，因整臂路线无法确认主动finish，已抓持离架但未完成搬运/装载。完整前缀复现和显式变式为零模型调用的控制诊断，两者失败；另0API held局部诊断完成，原POLICY_BUDGET表示人工计划结束而非API额度耗尽；均不算GPT尝试、正式配额或训练数据。正式已完成0/计划5，前置GPT完整成功gate未满足；没有随机化或训练。

代表视频都是完整同一次运行的H264 CRF23阅读派生，保留全部帧/顺序/分辨率/PTS，四条合计约12.40MB，像素不是native逐字节副本：

- [teacher首条完整成功](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_full.mp4)。
- [GPT04座口受阻完整失败](docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_04_rim_obstruction_full.mp4)。
- [GPT05 link6碰盖完整失败](docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_05_link6_collision_full.mp4)。
- [GPT06主动finish完整失败](docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_06_safe_finish_full.mp4)。

[媒体薄索引与回执](docs/lab_cuvette_loading/Project_v1_1/report/stage8_reading_media_index.json)保留native来源SHA、全部帧时间与解码/实际视觉QA范围。较早GPT03全片及v6双视局部不重复复制，选中Markdown经打包脚本转换为固定交付提交的GitHub链接；v6腕视局部也以固定GitHub链接追溯，原标签为TASK_INCOMPLETE。

模型输入只选少量实际JPEG、公开状态与manifest；没有复制整套perception目录，更不声称保存完整HTTPbody、全部memory或私有reasoning。P7固定ROI预览是离线准备，不能冒充模型实发。未来GPT07关键输入与视频仅在实际闭合后纳入，不留假成功或假媒体实体。

代码只选当前评分/collector/reader/控制契约片段及必要配置，供审阅而非完整可运行环境。10mm器皿是尺寸假设，real_calibrated=false；原native质量告警、cooked全局几何误差未知和GUI退出警告保留。仿真微米数值不代表真实硬件精度，回调力未独立标定。

大H5、raw日志、USD资产、环境、权重、历史包及凭据均不随包。成功H5全读、正常ACT/DP batch、自含性和替代路径验收见报告链接；JSON中本机源路径仅作出处，不表示文件在包内。完整数据另行交接，资产从固定锁及公开HF入口获取。继承的public_samples锁指向旧Project_v1样例，仅是来源依赖，不代表本轮七条教师H5已公开上传。

最终包保留repo相对层级，DOCX目标不改写；根目录文件清单记录实际提交和源/目标SHA，SHA256SUMS供传输核验。本轮打包前要补齐报告全页QA、GPT07原结果/费用、同源CI与最终推送证明；本草案不执行打包。
