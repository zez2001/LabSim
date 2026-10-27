# LabSim Project v1 1 当前结果阅读说明

先读[DOCX报告](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.docx)或[Markdown报告](docs/lab_cuvette_loading/Project_v1_1/report/LabSim_Project_v1_1_项目发布与验证报告.md)，再看[逐条结果CSV](docs/agent_handoff/Project_v1_1_current/current_results.csv)、[运行与资料提交范围](docs/agent_handoff/Project_v1_1_current/version_scope.json)和[版本使用入口](docs/lab_cuvette_loading/Project_v1_1/README.md)。生成时间{{GENERATED_AT}}、实际交付提交{{SOURCE_COMMIT}}、分支{{BRANCH}}；完整工程{{REPOSITORY_URL}}。

固定standard场景原计划五个0b独立teacher进程完整成功，另58da/9a/422/9a88各单次回归成功。最新9a88只跑了额外1条，不是该提交跑5次，不写9/5或随机泛化率。没有训练或随机化。

GPT01–08是八个不同调试条件，均未完整装载；正式评测未启动（已完成0/计划5），不能当正式0/5成功率。最新08真实P9、34决策/34网络请求、33物理动作加finish，终点65.116667秒。抓持、离架和持物搬运通过，三次100µm下降请求也执行了，但杯底仍高于座口约83.652mm、对A轴XY约34.993mm；仍属稳定搬运，不能称预插入或插入精度验证。模型因通行、深度/承托不确定主动结束，无support/open/retreat；post-retreat unavailable/stable null。离线几何没有输入模型，原depth/gap/overlap仍null。

当前代表媒体：

- [teacher首条完整成功](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_full.mp4)与[同次成功释放撤离腕部局部](docs/lab_cuvette_loading/Project_v1_1/media/reading/teacher_support_align_01_release_wrist_clip.mp4)。局部531帧/585269字节，对应108.016667–125.666667秒，只是LOCAL CLIP及teacher物理证据，不能替代GPT模型图或成绩。
- [GPT04座口滑移完整失败](docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_04_rim_obstruction_full.mp4)。本轮最远实际座口接触来自此旧调试，随后滑移。
- [最新GPT08完整未完成](docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_08_self_state_incomplete_full.mp4)。实际阶段图见[模型图索引](docs/lab_cuvette_loading/Project_v1_1/report/actual_model_stage_images.final.json)，未到support/open/retreat明确unavailable。

[媒体薄索引](docs/lab_cuvette_loading/Project_v1_1/report/reading_media_index.final.json)提供同次native来源、SHA、PTS、完整解码和真实关键帧QA；完整片保留全帧顺序/分辨率/PTS，局部只保留声明连续窗口且PTS移零。有损H264不保证像素相同。旧[GPT05碰盖全片](https://github.com/zez2001/LabSim/blob/487b282b7d1147f61d97c213d0b038a1d731e214/docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_05_link6_collision_full.mp4)、[GPT06主动结束全片](https://github.com/zez2001/LabSim/blob/487b282b7d1147f61d97c213d0b038a1d731e214/docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_06_safe_finish_full.mp4)、[GPT07主动观察全片](https://github.com/zez2001/LabSim/blob/487b282b7d1147f61d97c213d0b038a1d731e214/docs/lab_cuvette_loading/Project_v1_1/media/reading/gpt_debug_07_active_view_incomplete_full.mp4)固定到已实际资料提交，不重复复制。

[最终来源快照](docs/lab_cuvette_loading/Project_v1_1/report/release_snapshot.final.json)和[八次GPT分类](docs/lab_cuvette_loading/Project_v1_1/report/GPT_closed_cohort.final.json)区分task、安全、record完整性、physics可信和BC资格。有效失败可以分析，不进success BC；0API前缀/held诊断不是GPT成绩或完整任务训练数据。单集teacher H5约1.94GB，自含图像、正常success ACT/DP及替代路径读取已验；本包不含H5/raw、native大视频、环境、权重或完整perception。JSON里的本机路径是出处，不承诺包内存在；完整数据另交接。固定HF public_samples仍是旧Project_v1样例，不冒充本轮新数据。

P9只提供机器人自身名义FK与authored INPUT盒和通用提示，非单因素A/B；没有目标/器皿/环境距离、规划器或自动动作。自身盒、离线CAD都不是全局cooked或连续路线证书。公开指端触觉是杯筛选法向范数，不是摩擦/承托。保存的公开JSON/exactJPEG/静态prompt与工具回执不等于完整HTTPbody或私有memory。10mm/20g工程假设、real_calibrated=false、原native flags、真实GUI退出warning、力/像素时钟/cooked未知边界保留，微米仿真量不作硬件精度结论。

预算固定截至08为333次网络尝试/$27.894200，其中已知usage估价$26.485230与8次未知预留$1.408970分开；余$2.105800未耗尽，不是供应商账单。原finish关闭采集/进程且没有同episode resume，不通过回放、teacher或新reset冒充原尝试继续。保留旧Project_v1使用入口与历史记录；完整代码/资产按锁另取，Franka未知许可不套代码MIT。
