# V0_demo04 仪器朝向CPU复核

原装配几何铰链轴沿local X，Y≈−49.312mm；A座位于Y≈+147.629mm、B≈+43.629mm，因此local+Y为远离铰链的接近侧。原视频中A远铰链、B近铰链，角色对应一致，但厂家前面板名称及相机标定未确认。

标准布局instrument原点[.36,.18,.74]m、rack中心[−.04,−.22,.74]m；atan2(−.4,−.4)−90°模360得135°，Rz(135°)·local+Y=[−.7071,−.7071,0]，与原点到架中心方向一致。不是任意180°翻转。该判据从装配原点计算，A座自身到架中心仍约19.7°离轴，不冒充全路径对齐。

实际调用scene.add_scene组合内存USD，逐点核对全部8视觉实例及8碰撞输入只施加一次root yaw；A/B距离104mm保持，没有EngineeringAdapterA或NeighborInstrument。源CAD固有X90和mm→m归一化只在资产链内既有地处理一次，派生近90盖板同样不重复。本文件没有物理步、没有Isaac/GPU；仅静态朝向检查，不能代替原座配合或机械臂净空。

`instrument_orientation_top.png`为实际三角线投影的俯视标注图，不是Isaac渲染。全部来源SHA、矩阵和坐标见`geometry_orientation_audit.json`。
