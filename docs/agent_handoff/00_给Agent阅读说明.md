# LabSim Size_v1：本轮改动与结果

这是小阅读包，只收本轮尺寸变体、固定原座装载及采集结果。本轮最终审计为20条合格完整成功及20条有效受控提前停止失败（1/5/10/18mm各5条），没有自然失败或模型训练。完整H5、原始日志、35个派生USD实体、环境和检查点另行管理；旧阅读包、Env_v1与全部历史实验保留。

生成时间：{{GENERATED_AT}}（Asia/Shanghai）。分支：`{{BRANCH}}`。交付提交：`{{SOURCE_COMMIT}}`。

建议按顺序查看：

1. [本轮报告与录像](01_Size_v1报告与结果/)：DOCX、Markdown、表格和同级media；请传输整个目录，不能只传DOCX。
2. [状态与边界](02_本次改动与配置/状态与边界.md)及[最新实际结果快照](02_本次改动与配置/result_snapshot.json)：区分开发运行、正式固定5次、合格成功/失败、进程中断及未完成项。
3. [尺寸与几何结果](02_本次改动与配置/candidate_dimensions_and_geometry.csv)、[资产摘要](02_本次改动与配置/asset_summary.json)、[原座几何摘要](02_本次改动与配置/geometry_family_summary.json)及[实际烹饪探针](02_本次改动与配置/cooked_preview01_summary.md)。
4. [冻结标准场景配置](02_本次改动与配置/configs/standard.yaml)、[冻结依赖清单](02_本次改动与配置/configs/frozen_scene.json)、[正式已闭合首集的相机摘要](02_本次改动与配置/camera_actual_config_summary.json)、[实际物理记录定义](02_本次改动与配置/formal_standard01/physics_capture_meta.json)、[实际初态摘要](02_本次改动与配置/formal_standard01/initial_state_summary.json)及[冻结数据正常读取](02_本次改动与配置/formal_standard01/guarded_frozen_dataset_read.json)。首集证据不代替整批退出与最终配额审计。
5. [复现与采集命令](02_本次改动与配置/复现与数据读取.md)、[数据资格](02_本次改动与配置/data_qualification.json)、[40集独立核查](02_本次改动与配置/final_independent_checks.json)、[正式ACT单帧／DP三帧任务dataset读取](02_本次改动与配置/actual_training_task_dataset_batch.json)及[快照来源和哈希](02_本次改动与配置/version.json)。源路径是追溯信息，不表示大文件已经放进此小包。

阅读时保留以下事实：

- 原目标为同一个A座 `candidate_far_hinge`。原座、仪器与来源架的几何和物理参数保持不变；比色皿通过同一个XY仿射规则派生，高度67.5mm、底部基准不变，视觉与28块碰撞同步变换。尺寸是实验假设，不反推为实物尺寸。
- 35个候选覆盖9.5–12.5mm。10.70mm是当前采样中最大正的保守完整路径证书；10.72–11.00mm完整路径仍未认证，不能称为全部不可能。11.02mm及以上的入口排除只适用于声明的直立四个方位角及统一平移搜索规则，不是任意六自由度证明。
- 烹饪表示查询与真实物理射线抽样分别记录。preview中逐块双向表面抽样观察到约13.6–14.0μm差异；原座射线表面最大观察距离约44.7nm。两者都不是全局误差上界或真实接触精度，静态完整烹饪网格读回及部分速度告警仍有局限。
- 完整任务成功必须有实际插入、承托交接、张爪、脱指撤离及至少3秒独立稳定。只使用最终独立评分；几何通过、preview、预插入或夹持中稳定均不算完整装载成功。
- 正式采集以冻结场景及完整元数据准入为准。开发阶段成功可能因缺冻结H5指纹而不计20条；自然失败与确定性动作偏差分组，预检、初始化、服务、短预算接口诊断及进程中断单独归档。没有最终审计时，数量为未知，不能提前宣称已有40条。
- collect、train和训练内自动验证均固定standard；训练随机种子另行配置，不等于场景随机化。random10已经取消，不列为待完成验收项。本轮未要求三种模型重新对比或开展训练。
- 训练成功BC默认只读取合格成功。轻索引使用同collection树的相对H5链接，移动时应传输整棵collection树；单条原始episode H5仍独立。完整便携episode另外提供，不包含在此小包。

[对应交付提交的工程]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。包根 `文件清单.json` 和 `SHA256SUMS.txt` 记录实际交付内容。实际采集数、固定5次结果及未解决项请以快照和最终报告为准。
