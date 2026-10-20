# LabSim V0 demo03 视频场景适配实验结果

日期2026-10-20，分支`codex/lab-cuvette-demo03`，独立模式`video_demo_adapted`。

已经实际取得首条连续成功轨迹`outputs/lab_cuvette_loading/V0_demo03/dev_03/trial_00`，仿真61.75秒。独立15项检查全部通过，H5与独立资格一致；撤离后58.65–61.75秒连续3.1秒稳定，三手部输入包络的实际位姿净空保守下界112.265mm。原CAD配套与真实标定仍为false。

采用完整白色6×6参数化架和腔内A派生适配座；器皿保持原尺寸，B及其余仪器结构保留。源架、孔壁、底面及蓝色F6邻物参与物理碰撞。支撑交接前停止下降，逐步卸载后实际松爪，先抬手60mm再横撤120mm。实际器皿XY反馈修正机器人位置跟踪偏差，未使用器皿瞬移、吸附、冻结或运行中关闭碰撞。

前两条失败均保留：dev_01搬运时link6碰盖板；dev_02插入前实际X偏差约−.674mm，超过.575mm单侧名义余量，入座受阻后相对TCP上滑，最终保守接近事件停止。没有调整50µm穿透门槛或重新把失败标成功。

当前已完成首条演示，正在进行固定5次、之后的随机10次及现有加载器成功batch读取。此处暂不填写未执行的批次成绩，最终报告将补入实际结果。

[资产改动](asset_changes.json)、[最终尺寸](dimensions.csv)、[ChemLab定向参考](source_and_assumptions.md)、[整臂计划检查](evidence/arm_plan_03.json)、[几何计划修订](geometry_plan_revision.md)、[运行命令](../../../demos/lab_cuvette_demo03/README.md)。
