# GPT07原A座几何定位（仅离线）

基于已实际退出的GPT07原始物理姿态、锁定CAD和机器人自身USD/URDF重算，不启动仿真，不改原始null字段或标签，不给模型输送这些真值坐标。`selected_position_geometry.csv`区分终态、全轨迹最近XY及最近3D样本；原座几何轴与既有偏置加载轴分开报告。负“轴向深度”只表示仍在原座口上方，不能当作已经进入孔内的测量。

原A座SourceMesh3实际三角面重新求中心承托面和口沿高度，完整累计变换与毫米/米单位见`summary.json`。最低杯底由实际视觉源网格和原记录的姿态核对，不依据TCP。原depth/bottom-gap/input-overlap未知值全部保留。

`robot_to_lid_input_surface_checks.json`检查选定实际姿态的link6、link7、hand、左右指与SourceMesh5盖板输入面；实际joint9的URDF FK先与原实际TCP核对。材质输入三角面与重建声明凸包分别计算，采用点到三角面、边到边及三角面SAT，保存面索引和最差点。不是最近顶点距离，不是PhysX烹饪表面读回。它不验证连续未来路线或全部机器人/环境配对，不将静态间距改写成可安全下降。

单独的P9 robot-self局部盒仅包含机器人自有输入，与本目录有意分开。禁止把本目录中的器皿/座/盖板坐标与距离接入GPT观察或提示词。
