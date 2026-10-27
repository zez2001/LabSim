# LabSim Project v1 1 当前结果阅读说明 草稿

当前是只读打包计划，没有生成桌面包或最终报告。本稿cohort截至07；P9/GPT08最终闭合证据、教师回归及最新媒体待纳，不补造尚未引用的结果。最终时间{{GENERATED_AT}}、实际交付提交{{SOURCE_COMMIT}}、分支{{BRANCH}}；完整工程{{REPOSITORY_URL}}。最终交付SHA由真实包清单生成，不预填未来提交。

最终先读[DOCX报告](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.docx)或[Markdown报告](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.md)，再看[逐条结果CSV](docs/agent_handoff/Project_v1_1_current/current_results.stage9.draft.csv)及[运行代码与公开证据提交范围](docs/agent_handoff/Project_v1_1_current/version_scope.stage9.draft.json)。正式发布前更新本说明及实际报告，不用草稿充成品。

原计划teacher五个独立固定standard进程均完整成功；另58da/9a/422各一条回归成功，单列不称8/5或随机泛化率。GPT01–07是七个不同debug，均未完整成功。最新07为真实P8、46决策/46请求、45物理动作加finish；抓持、离架、持物搬运通过，但因下降净空、深度/承托不确定主动结束，原TASK_INCOMPLETE，无释放/撤离，post-retreat unavailable/stable null。正式0/计划5，前置完整GPT成功gate未满足。没有训练或随机化。

当前代表媒体：

- [teacher首条完整成功](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_full.mp4)与[同次释放撤离腕部局部](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_release_wrist_clip.mp4)。后者是531帧/585269字节的LOCAL CLIP，对应108.016667–125.666667秒，不能称完整运行。
- [GPT04座口滑移完整失败](docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_04_rim_obstruction_full.mp4)。
- [GPT05碰盖完整失败](https://github.com/zez2001/LabSim/blob/487b282b7d1147f61d97c213d0b038a1d731e214/docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_05_link6_collision_full.mp4)。
- [GPT07主动观察完整未完成主片](https://github.com/zez2001/LabSim/blob/487b282b7d1147f61d97c213d0b038a1d731e214/docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_07_active_view_incomplete_full.mp4)。

[薄媒体索引及原回执](docs/lab_cuvette_loading/Project_v1_1/report/stage9_reading_media_index.json)记录同次来源、SHA、全帧/PTS、完整解码与实际视觉QA。它们均为有损阅读派生；完整片保留所有帧/时序，局部只保留声明连续窗口、PTS起点移零。旧05/06/07全片和更早代表只留固定487b Git链接，不重复复制；native视频/H5/raw不随包。

[offline geometry v2](docs/lab_cuvette_loading/Project_v1_1/diagnostics/gpt_debug_07_offline_geometry/summary.v2.json)用闭合姿态/CAD解释仍未到座底，原终态depth/gap保持null，衍生距离不回填标签、不提供模型。mesh/hull/自身INPUT盒并不认证cooked或全局路径。P9追加公开机器人自身名义FK/局部盒及通用接触提示，不是单因素A/B；不含环境/目标/器皿距离、规划器或自动动作。CI43成功与CPU/独审不等于P9任务成功。

包只选少数实际JPEG/公开状态/manifest和控制器、动作CSV、正常成功/失败reader证明、评分/collector/reader契约及配置；不是完整工程/环境，也没有整套perception、完整HTTP或私有memory。继承的public_samples锁是旧Project_v1样例，不代表本轮8条teacher H5已公开上传。大数据单独交接；JSON本机路径只是出处，资产按固定锁另取，Franka许可未知不套代码MIT。

当前预算只截07闭合的299尝试/$24.843530，其中8次未知usage预留保留；不是正在运行08的余额或供应商账单。旧标签/null、10mm工程假设、real_calibrated=false、native告警、GUI退出warning及cooked/真实力未知边界保留。仿真微米量与名义模型一致性不能当硬件精度。

最终包目标≤25MB，保留repo相对层级以保持DOCX本地目标。等实际08/teacherP9闭合及预算、source/CI后，root完成报告author和逐页QA、提交推送核远端、更新当前交接入口，转成真正manifest后在新桌面目录打包；核链接、媒体、源/目标SHA和SHA256SUMS。未知P9媒体/成功不预填。
