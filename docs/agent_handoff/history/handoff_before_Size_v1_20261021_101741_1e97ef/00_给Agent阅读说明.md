# LabSim Env_v1 本轮改动与结果

这是本轮的小阅读包，目标小于20MB。只包含Env_v1报告、自带media、本轮摘要和配置；不包含整套历史、outputs、H5、环境或checkpoint。旧阅读包及V0至demo04保留。

生成时间：{{GENERATED_AT}}（Asia/Shanghai）。分支：`{{BRANCH}}`。交付提交：`{{SOURCE_COMMIT}}`。

建议先阅读：

1. [本轮报告目录](01_Env_v1报告与结果/)：包含DOCX/Markdown报告。报告的视频和图片位于同级[media](01_Env_v1报告与结果/media/)，请传输整个文件夹。
2. [状态与边界](02_本次改动与配置/状态与边界.md)和[完成矩阵](02_本次改动与配置/completion_matrix.json)：区分实际通过、失败、仅有接口及未执行内容。
3. [最新82.65秒预插入结果](02_本次改动与配置/preinsert_continuous_latch01_result_summary.json)、[42.3秒历史失败](02_本次改动与配置/extract_continuous_latch01_control_summary.json)及[相机关联摘要](02_本次改动与配置/camera_sync_summary.json)。
4. [三条真实策略链路摘要](02_本次改动与配置/three_policy_chains_summary.json)、[真实API摘要](02_本次改动与配置/live_environment_api_validation_summary.json)及[正式短动作回放结果](02_本次改动与配置/replay_astra03_01_actual_summary.json)。
5. [当前配置](02_本次改动与配置/configs/)、[资产清单](02_本次改动与配置/current_asset_scene_manifest.json)、[尺寸表](02_本次改动与配置/current_dimensions.csv)、[原版本保护](02_本次改动与配置/previous_versions_protection.json)及[快照来源与哈希](02_本次改动与配置/version.json)。JSON中的工程source/evidence字段是可追溯来源，不表示这些大文件都在小包内。

必须保留的结果边界：

- **完整原座装载仍未完成。** 最新82.65秒/4958控制步预插入诊断已通过来源清槽、物理抓取、搬运、预对准和持物回退，诊断task_success=true；没有原座插入、松爪和脱指撤离，full/native_pair仍null。架内双指静持3秒仅为更早的历史子任务，不能与该新结果混淆。
- 42.3秒continuous_latch旧试验已完成清槽搬运，但3秒窗口漂移230.445μm未达到原200μm门槛，整体false原样保留。最新zeroDelay预插入4958/4958腕相机渲染位姿匹配当前USD；这不等于真实物理精度或光学校准。
- 原A/B座入口存在材料几何冲突；12.6mm只是部分中央截面参考宽，不是完整入口/全深度净空。没有扩大孔、删凸起、缩小碰撞或放宽穿透阈值。
- π0.5、GPT-6 Astra direct、真实RLinf/RPent Harness均已执行真实图像→模型→动作→后继观测。每条仅5个策略动作、0.25秒，task_success=false；这是接口接通，不是120秒性能评测、成功率或完整装载失败配额。
- 保留Astra01工具发现失败与Astra02元数据边界不合格；最终合格direct样例为Astra03。旧RPC原始get_camera_meta含debug；后续源代码default getter修复有CPU验证，最终03/Harness实际净化tool边界合格。
- random seed7检查只验证B1合法初始化、同seed复位及整机/架体装配关系，不是random任务批次。真实标定、完整固定5次/random10次和20成功+20有效失败尚未完成。
- 正式replay入口已实际回放Astra03的15个控制周期并正常退出；这是0.25秒短诊断动作回放，重新独立评分false，没有新模型推理。**完整loading成功/有效失败配额保持0/0。**

参考原始视频和四张照片来自本机`/home/wujing/Desktop/来自远程/20261013`；本轮可离线查看的对照截图以报告及其media为准。Franka为机器人代理，布局是视频关系估计，器皿12.5×12.5×67.5mm为用户名义尺寸，20g质量是假设，real_calibrated=false。

最新便携数据另存桌面`LabSim_Env_v1_便携数据_preinsert01_20261021`，2546460010字节，**不在这个小阅读包**；[导出与读取摘要](02_本次改动与配置/portable_export_summary.json)保留原标签、无外链和ACT/DP读取结果。旧extract01约451MB便携数据仍保留。需要检查完整episode时另行传输，不能将预插入诊断成功理解为成功装载数据。

[对应提交的工程]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。包根`文件清单.json`记录最终分支/提交、来源及SHA256，可用`sha256sum -c SHA256SUMS.txt`核验。配置和资产的完整运行依赖从工程获取，小包用于阅读结果。
