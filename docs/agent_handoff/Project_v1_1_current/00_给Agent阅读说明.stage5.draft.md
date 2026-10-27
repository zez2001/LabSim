# LabSim Project v1 1 本轮结果阅读说明 草稿

此文件和配套清单用于最终包准备，尚未生成桌面包或最终DOCX。生成时间{{GENERATED_AT}}，候选提交{{SOURCE_COMMIT}}，分支{{BRANCH}}；最终打包前须检查实际发布SHA、CI和所有运行准入。完整工程从{{REPOSITORY_URL}}获取。

先看[本轮报告输入草稿](docs/lab_cuvette_loading/Project_v1_1/report/release_inputs.stage5.draft.json)。最终DOCX/Markdown将在真正author和全页QA后加入，不用本草稿冒充成品。

当前已确认一条teacher完整成功，实际代码0b922ec，10×10×67.5mm尺寸假设器皿、原座不变。完整录像是[首条teacher成功主片](docs/lab_cuvette_loading/Project_v1_1/media/teacher_support_align_01_full.mp4)，配有[独立支撑和便携验收](docs/lab_cuvette_loading/Project_v1_1/diagnostics/teacher_support_align_01_support_portability_audit/README.md)。首条成功不代表已完成5/5，也不是GPT或真实硬件成功。

[GPT04完整失败主片](docs/lab_cuvette_loading/Project_v1_1/media/gpt_debug_04_rim_obstruction_full.mp4)来自另一实际runtime63410bf，原GRASP_SLIP、未释放或撤离。其[全部公开输入与动作](docs/lab_cuvette_loading/Project_v1_1/diagnostics/gpt_debug_04_perception/README.md)保存51个公开JSON/102张exact JPEG、静态prompt/schema与公开回执，不含完整HTTPbody、完整memory或私有reasoning。P5视觉记忆目前只有CPU证据，旧GPT04实际是P4。GPT05及后续重复待闭合后更新，不能补造结果。

[baseline6腕视片段](docs/lab_cuvette_loading/Project_v1_1/media/teacher_baseline_close_01_support_release_wrist_clip.mp4)是明确的局部失败对照，不是完整成功。历史GPT03全片和baseline双视片不纳默认小包，正文改为小证据/固定SHA历史出处，防止体积无节制增长。

原成功H5约1.944GB，SHA b346f1788eee027648dd5e483d6630d340d8be6d5b4af867d8cdda2ba1381a7c，不在小阅读包。正常ACT/DP成功batch、无外部HDF5依赖及替代路径验证见验收JSON。JSON里的源机器绝对路径只是出处，不表示包内有该数据或完整Isaac运行环境；完整数据需另行传输。

包候选保留repo相对层级。报告位于docs/lab_cuvette_loading/Project_v1_1/report时，到root config为四层；若改报告输出子目录，由builder实际计算并重新核链接。原始config、资产锁、公开sample清单只用于复现出处，不把旧sample冒称本轮新成功H5。

最终包硬限80,000,000未压缩字节。优先teacher1/GPT04/GPT05三条最新主片和必要腕视失败局部；超限时先排除历史全片，再按真实事件导出并标注代表失败片段，同时更新正文与manifest，不留缺失视频引用。原始raw/H5/环境/权重/旧包/凭据均不复制。最终会给文件清单和SHA256SUMS供传输核验。
