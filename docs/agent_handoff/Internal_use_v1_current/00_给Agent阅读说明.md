# LabSim 本次文档与内部使用优化

本包只包含2026年10月28日本次改动和结果，生成时间：{{GENERATED_AT}}。

源码：[LabSim](https://github.com/zez2001/LabSim/tree/codex/labsim)，分支 `{{BRANCH}}`，发布提交 `{{SOURCE_COMMIT}}`。最终远端与CI实查见随包 `publication.json`；逐文件来源与SHA256见`文件清单.json`和`SHA256SUMS.txt`。

阅读顺序：

1. `本次改动与结果.md`或简短DOCX：修改、实际验收、剩余问题。
2. `使用指南/README.md`及`使用指南/ONBOARDING.md`：准备环境、完整任务、采集、ACT/DP读取和策略。
3. `media/teacher_full.mp4`：本次普通Teacher入口的原始连续双视角录像。
4. `evidence/teacher/`：实际运行提交、独立结果、H5完整读取、正式ACT/DP batch、时间戳与退出凭据。
5. `evidence/data_usage/`及`evidence/input/`：用途筛选、历史保护、移交和实际tokenizer核查。

GPU实际运行代码为`5c6b6422f9ba6fc16ac7b4374799c5ed7e426e47`；后续提交为索引/输入可观测性、文档和交付整理。该运行使用`Project_release_v1`、原HF revision、10mm尺寸假设资产及原内部A座。

完整H5、资产和模型权重不在阅读包中。来源、大小与哈希在证据内；完整项目从GitHub获取，场景资产从锁定HF版本下载，正常使用可按指南重新采集。相对外链索引不是独立数据文件，移交原数据须按数据指南带齐依赖或生成copy文件。

本包不重复打包旧实验报告和旧策略视频。历史数据用途审计复用已有记录；任务文本token是相同部署源码的本地重建，新服务开始直接记录处理后的有效输入。场景与控制基线、原始标签、历史结果和原资产保持。
