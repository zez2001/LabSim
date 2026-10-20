# LabSim V0 demo03 视频场景适配实验结果

日期2026-10-20，分支`codex/lab-cuvette-demo03`，独立模式`video_demo_adapted`。

已经实际取得首条连续成功轨迹`outputs/lab_cuvette_loading/V0_demo03/dev_03/trial_00`，仿真61.75秒。独立15项检查全部通过，H5与独立资格一致；撤离后58.65–61.75秒连续3.1秒稳定，三手部输入包络的实际位姿净空保守下界112.265mm。原CAD配套与真实标定仍为false。

采用完整白色6×6参数化架和腔内A派生适配座；器皿保持原尺寸，B及其余仪器结构保留。源架、孔壁、底面及蓝色F6邻物参与物理碰撞。支撑交接前停止下降，逐步卸载后实际松爪，先抬手60mm再横撤120mm。实际器皿XY反馈修正机器人位置跟踪偏差，未使用器皿瞬移、吸附、冻结或运行中关闭碰撞。

前两条失败均保留：dev_01搬运时link6碰盖板；dev_02插入前实际X偏差约−.674mm，超过.575mm单侧名义余量，入座受阻后相对TCP上滑，最终保守接近事件停止。没有调整50µm穿透门槛或重新把失败标成功。

首条演示之外，固定5次已全部独立通过，H5资格一致；现有MinimalPickDataset已实际读取成功batch。固定批处理外壳在末尾汇总阶段返回143，任务五条均完成；原空summary保留，summary_recovered_01只读汇总确认5/5。原因未确证，不将该退出吞成正常零退出。随机10次尚未执行，接下来顺序运行。主展示相机已通过投影检查拟改为1.3cm以完整容纳白架；双视角观测、控制、物理、尺寸及50µm判据不变，新宽视角仍待实际录像验证。最终报告将补入实际结果。

[资产改动](asset_changes.json)、[最终尺寸](dimensions.csv)、[ChemLab定向参考](source_and_assumptions.md)、[整臂计划检查](evidence/arm_plan_03.json)、[几何计划修订](geometry_plan_revision.md)、[运行命令](../../../demos/lab_cuvette_demo03/README.md)。
