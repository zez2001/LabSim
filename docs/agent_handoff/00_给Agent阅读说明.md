# LabSim 结果阅读包 先读说明

这是截至 V0_demo02 的结果交接。最新目标是从完整白色多孔架取出器皿，并在开盖后的样品腔内部装载；本轮尚未完成这条连续物理任务。已有机外工程演示保留为历史，不替代新目标。

生成时间：{{GENERATED_AT}}（Asia/Shanghai）。分支：`{{BRANCH}}`。来源提交：`{{SOURCE_COMMIT}}`。

## 先看本轮新增证据

1. 阅读 [V0_demo02 报告 Markdown](03_V0_demo02场景核查/report.md) 或 [本轮 DOCX](03_V0_demo02场景核查/LabSim_V0_demo02_场景与装载关口报告_20261020.docx)。
2. 对照 [原视频角色核查](03_V0_demo02场景核查/reference_review/reference_review.md)、[Isaac静态参考图](03_V0_demo02场景核查/static_review/reference.png)、[腔内近景](03_V0_demo02场景核查/static_review/chamber.png)。静态器皿是unsupported preview，不是自然支撑或装载成功。
3. 查看 [资产对应CSV](03_V0_demo02场景核查/asset_correspondence.csv)、[源尺寸](03_V0_demo02场景核查/source_audit/dimensions.csv)、[最终场景尺寸与变换](03_V0_demo02场景核查/source_audit/final_scene_verification.json) 和 [原配几何相交见证](03_V0_demo02场景核查/source_audit/candidate_original_pair_sections.png)。
4. 核对 [验收状态](03_V0_demo02场景核查/acceptance.json)、[判分/采集接口实测范围](03_V0_demo02场景核查/data_audit/README.md)、[集中待补资料](03_V0_demo02场景核查/required_information.json)。

## 最新事实与当前阻塞

原视频实际显示6×6完整白色架、两台开盖仪器；任务终点为前景仪器黑色腔内较远铰链的金属框座A，另一座B上有透明/粉色物。6×6来自双视角图像计数，不是CAD或实物尺寸测量。

本机相关交付核查仍未找到完整架体CAD。现有newnew4.usd普通遍历会漏掉网格，深层实例代理检查确认8个实际网格，包含机身、盖板、两原座及小部件，没有隐藏完整架。视频A/B与CAD远/近铰链候选的关系仅为暂定，厂家身份和型号配套未知。

原盖板主面41.566965°；新派生层绕几何推测的铰链X轴刚体增转48.433035°，形成视频近竖直外观的90°估计姿态。保留源文件与全部原部件尺寸。机身520.5×630×230mm不变，源开盖整体高435.481mm，派生姿态整体高577mm，应分开理解。

原器皿约14.85mm外宽，两座顶部特定中央截面间距约12.6mm；实际原三角面在声明的居中直立下插姿态下各有40个高度的表面相交见证。没有缩模、扩大孔、删除原座或用机外槽替代终点。局部剖面/射线不是完整手爪路径或PhysX烹饪几何证明。

已运行的是源/最终场景离线审计、独立USD保存重载、Isaac四视角零任务步静态渲染，以及新判分/采集元数据、历史H5只读和新空索引拒绝检查。新场景完整轨迹、标准5次、随机10次、成功H5及一个成功训练batch均未执行。真实质量、材料、机器人动力学和实物几何未校准。

后续集中补充三项：完整白架文件及装配入口；A/B身份、实际插入方向及型号配套；器皿/座全深度尺寸、承托高度、公差和开盖/铰链依据。明细见本轮required_information.json。

## 历史结果应如何使用

[系列总报告](01_系列实验背景/report.md) 截止ext02，涵盖最小抓取、采集/回放、合成亚毫米插入、V0代理任务及外部资产接入。原先6×8是V0合成选择，最新视频计数证据为6×6。

[V0_demo01报告](02_V0_demo01连续装载/report.md) 保留新增机外工程工装下的连续流程：同初态固定5/5、小范围布局随机2/3。该成功不属于V0_demo02正确腔内场景，也不是原CAD配套成功。可看 [历史完整工程录像](02_V0_demo01连续装载/media/engineering_workflow_success_1080p.mp4) 和 [历史随机失败录像](02_V0_demo01连续装载/media/random7000_release_failure.mp4)。

seed7000仍是50.289µm源几何穿入超过50µm门槛的失败，旧评分及原H5不改。新分析把末3秒称terminal_window；撤离前失败的post_retreat_window为unavailable，撤离后稳定与撤离净空为null。见 [语义修正](03_V0_demo02场景核查/data_audit/seed7000_semantics_v2.json)。

本包19段视频全部是明确标注的历史代表录像或片段，没有V0_demo02新连续任务录像。不同版本的成功/失败、场景对应、原CAD配套和真实标定不可合并。

## 传输与来源

本包是报告、图表、录像、结果和精简证据的独立文件副本，可整体传输。不是完整工程、环境或原始数据包。三个版本文件夹均可离线阅读；包外源码引用转换为对应提交的GitHub链接。`文件清单.json`记录原路径、源SHA256、包内SHA256及链接转换；`SHA256SUMS.txt`可用 `sha256sum -c SHA256SUMS.txt` 核验传输完整性。

原工程：`/home/wujing/Desktop/vla/LabSim`。历史原始H5/接触轨迹仍在 `outputs/lab_cuvette_loading/V0_demo01/`，本轮静态及接口结果在 `outputs/lab_cuvette_loading/V0_demo02/`。绝对路径用于追溯，不表示接收者本机存在这些文件。

[完整源码及本包来源提交]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})。仓库私有，源码链接需要访问权限。每次改进后会创建新阅读包，已有包保留。
