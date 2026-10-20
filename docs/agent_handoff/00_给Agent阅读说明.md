# LabSim 结果阅读包 先读说明

最新版本V0_demo04修正了12.5 mm器皿、单台仪器和朝向，保留原12.6 mm座及原CAD凸起。**完整装载尚未完成**。A/B座均存在原网格材料干涉；没有扩孔、删凸起或用16 mm座替代。实际完成一条76.917秒受限诊断和两条搬运失败记录；固定5次、随机10次完整任务未启动，成功训练episode为0。

生成时间：{{GENERATED_AT}}（Asia/Shanghai）。分支：`{{BRANCH}}`。来源提交：`{{SOURCE_COMMIT}}`。

## 先看本轮

1. [最新DOCX](05_V0_demo04原座核查/LabSim_V0_demo04_原座装载核查报告_20261020.docx)或[Markdown报告](05_V0_demo04原座核查/report.md)。
2. [同次连续1080p录像](05_V0_demo04原座核查/media/preinsert_diagnostic_03_main.mp4)：架内抓取、实际拔出、搬运、低速接近、原座上方停止、上抬10 mm并保持。**没有插入、松爪、完全撤离或释放后稳定**。[实际H5观测近景](05_V0_demo04原座核查/media/preinsert_diagnostic_03_obs256_camera2_65s_end.mp4)源分辨率256×256；原展示近景受手爪遮挡，不能作为精细接触证据。
3. [单台仪器/6×6架静态截图](05_V0_demo04原座核查/scene_check/README.md)、[尺寸表](05_V0_demo04原座核查/dimensions/dimensions.csv)、[器皿视觉与碰撞派生](05_V0_demo04原座核查/vessel/README.md)及[原座凸起干涉定位](05_V0_demo04原座核查/geometry/refined_02/README.md)。
4. [全部实际运行与未执行批次](05_V0_demo04原座核查/results/summary.json)、[逐次CSV](05_V0_demo04原座核查/results/runs.csv)、[首次搬运失败录像](05_V0_demo04原座核查/media/failure_transport_main.mp4)及[慢速搬运失败片段](05_V0_demo04原座核查/media/failure_02_held_deviation_last5s.mp4)。两次失败与最终受限诊断采用不同控制版本，不构成固定重复成功率。
5. [完整episode](06_V0_demo04完整诊断episode/episode_data.hdf5)和[数据先读](06_V0_demo04完整诊断episode/README.md)。885,164,015字节，4615控制转换，52个源数据集完整哈希核验，无外链/软链/VDS/外部存储。双视角RGB、动作、实际状态、阶段、槽位/座ID、完整双指命令与逐步effort记录齐备；原生/差分速度均保留。另有压缩逐物理步和原生接触记录，以及实际配置/初态/独立判分/源代码哈希。

H5 complete=true仅表示闭合完整记录。workflow_success/native_pair_success/data_eligible/real_calibrated均为false。正常成功过滤器按预期拒绝；现有getitem/collate的显式诊断读取核对首、中、尾及padding通过，未训练模型。`read_batch.npz`是读取样本，完整数据是H5本体。未完成释放撤离，post_retreat_window不可用，释放后稳定为null；末段terminal_window包括实际上抬运动。

## 历史资料与限制

[01系列报告](01_系列实验背景/report.md)截止ext02；[02 demo01](02_V0_demo01连续装载/report.md)为机外工程工装；[03 demo02](03_V0_demo02场景核查/report.md)为原尺寸场景核查；[04 demo03](04_V0_demo03视频适配/report.md)为14.85 mm旧器皿和腔内16 mm派生座的历史成功任务。其固定5/5及小随机10/10仅适用于旧适配配置，不能覆盖本轮修正尺寸与原座验证。原seed7000和各失败记录保留。

本轮器皿12.5 mm和中央座宽12.6 mm为用户提供名义尺寸；高度67.5 mm、质量20 g、摩擦与机器人参数未真实标定。白架110×110×28 mm、36个16 mm方槽为视频参考下的参数化假设；没有原架CAD或真实尺寸声明。仪器继承此前近90°开盖派生状态，整体绕Z135°朝向架中心。原生座内伸结构的真实功能及刚柔性未知；原座烹饪表面/offset未完整读回，不宣称已排除穿透或达到50µm控制精度。

## 传输与继续工作

请传输整个文件夹，不单独发送DOCX。Word中的视频为外部相对链接，包内MP4可直接播放；文件存在与解码通过不保证所有在线预览器都支持点击。根目录`文件清单.json`和`SHA256SUMS.txt`记录来源、实际提交和SHA，执行`sha256sum -c SHA256SUMS.txt`核对。

[源码及提交]({{REPOSITORY_URL}}/tree/{{SOURCE_COMMIT}})，原工程为`/home/wujing/Desktop/vla/LabSim`，GitHub当前显示仓库公开。完整H5在阅读包中，未上传Git；代码、配置、派生资产、报告及必要视频在对应分支。后续需集中确认原座内伸结构用途/刚柔性/行程、器皿全轮廓公差，以及承托基准和真实装载姿态，不重新要求用户选择已确认的A/B角色。
