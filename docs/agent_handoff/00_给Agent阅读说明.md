# LabSim 结果阅读包 先读说明

最新交付是V0_demo03视频场景适配：从完整白色6×6架抓取原尺寸器皿，进入开盖仪器样品腔A派生座，完成支撑交接、实际松爪、撤离和3.1秒稳定。固定复测独立成功 5/5，小范围随机独立成功 10/10，另有1次随机运行中断未评分并保留。已实际读取主片同源的训练格式batch，未训练模型。

生成时间：{{GENERATED_AT}}（Asia/Shanghai）。分支：`{{BRANCH}}`。来源提交：`{{SOURCE_COMMIT}}`。

## 建议阅读顺序

1. [最新DOCX](04_V0_demo03视频适配/LabSim_V0_demo03_视频场景适配结果报告_20261020.docx)或[Markdown报告](04_V0_demo03视频适配/report.md)。
2. [完整主录像](04_V0_demo03视频适配/media/random8000_full_view/main_h264.mp4)和[同次腔内近景](04_V0_demo03视频适配/media/random8000_full_view/closeup_h264.mp4)。这是同一个seed8000从来源初态到撤离后稳定的连续记录，其他片段注明来源。
3. [原视频与全架对应](04_V0_demo03视频适配/media/random8000_full_view/reference_scene_correspondence_vertical.png)、[腔内A对应](04_V0_demo03视频适配/media/random8000_full_view/reference_internal_A_correspondence_vertical.png)、[资产来源与假设](04_V0_demo03视频适配/source_and_assumptions.md)及[尺寸CSV](04_V0_demo03视频适配/dimensions.csv)。
4. [18条完整结果及1条中断](04_V0_demo03视频适配/results/final/results.csv)、[逐条判分与版本](04_V0_demo03视频适配/results/final/README.md)、[批次数据验收](04_V0_demo03视频适配/data_audit/formal_batch_audit_tool.md)。18条完整记录包括2条开发失败、1条开发成功、5次固定与10次随机，另有seed8008运行中断1条未评分；不把开发尝试或中断混进正式批次。
5. [真实batch精简样例](04_V0_demo03视频适配/data_audit/main_sample_data/README.md)、[主片完整控制时序](04_V0_demo03视频适配/data_audit/random8000_trajectory/README.md)及[动作语义](04_V0_demo03视频适配/data_audit/action_scope.md)。约360KB的batch是实际两个时点，不是完整episode；完整CSV保留全部控制周期和辅助力上限。

## 事实与限制

白架是视频行列/外观参考下的Python参数化设计，110×110×28mm、36个真实开口。A座按用户确认在原腔内位置重建16×16mm通道，保留原器皿、机身、B座和盖板派生姿态。ChemLab四种架只作定向结构参考，没有导入模型或代码。不是实测复刻，native_pair_success和real_calibrated仍为false。

随机只覆盖A1、A2、B1、B2、C1各两次及装配XY±1mm平移，yaw/槽内扰动为0；不代表全部36槽或真实成功概率。控制使用实际物体位置反馈，无视觉模型。8维action未包括阶段化夹指effort上限，重放须复用阶段控制或CSV/NPZ辅助指令；batch可读取不等于策略已学会自主装载。

开发失败保留：[搬运碰盖板录像](04_V0_demo03视频适配/media/dev_01_failure/main_h264.mp4)、[入口受力和夹持滑移诊断](04_V0_demo03视频适配/data_audit/dev02_contact_diagnosis/README.md)。固定批处理外壳在5条已完整保存后的汇总返回143，原因未知，另只读汇总确认5/5。原seed8008工具会话143中断停在INSERT，没有评分，原目录保留，同seed在新恢复目录完成，单独列出而不算物理失败。原生与差分速度差异、烹饪表面/offset完整回读未知等告警没有删除；50µm源几何门槛未放宽。

## 历史资料

[01系列报告](01_系列实验背景/report.md)截止ext02，涵盖抓取、采集/回放、合成偏差插入和资产接入；[02 demo01](02_V0_demo01连续装载/report.md)是机外工程工装，固定5/5、小随机2/3；[03 demo02](03_V0_demo02场景核查/report.md)是正确场景和原配尺寸冲突核查，未完成连续装载。旧视频和评分各保留所属范围，不改写seed7000原50µm门槛失败。demo03开发首条成功的1.6cm展示相机存在架角裁切，最终主片改1.3cm完整视野，物理与H5观测相机未改。

## 传输与继续工作

这是报告、录像、结果和精简证据的独立文件副本，四个文件夹可离线阅读。不是完整工程、环境或原始大数据包。`文件清单.json`与`SHA256SUMS.txt`记录来源和传输校验；执行 `sha256sum -c SHA256SUMS.txt`。完整原始H5/双视角/接触在原工程outputs独立目录，本包不含。

原工程 `/home/wujing/Desktop/vla/LabSim`；[源码及来源提交]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。仓库私有，源码链接需要权限。后续实测校正集中于架体尺寸、器皿与原座全深度配合/承托/型号、质量摩擦驱动响应及相机/盖板标定；这些事实不阻塞本次独立适配任务。
