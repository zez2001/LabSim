# 可见盖板与 SourceMesh5 对应补充

本补充保留先前 summary/manifest 字节不变。使用该闭合 GPT05 config 实际引用的原 USD，在 CPU 内存组合同一变换，不启动 SimulationApp、渲染、物理或 API。

SourceMesh5 对应的可见节点是 `/World/Instrument/Visual/Source/newnew4/newnew4/tn__3_ZBFi3j3/tn__8_x1iBOa1g0Jv0g7n4/Mesh`。两个节点均为 2,069 顶点；逐点世界坐标最大差 2.943916842e−8 m（约 29.4 nm），双向最近顶点最大差相同。这个数仅表示 authored 源数据转换一致性，不能写仿真运动、碰撞表面或实物精度。

原非零冲量点到可见三角面距离 1.755726396e−7 m（约 0.176 µm），最近面位于 x=0.259312388 m、z=1.313–1.317 m 的盖板顶缘。可见节点 AABB 与 Collision 层一致：[(0.259312388,−0.180250000,0.948000006),(0.476742007,−0.032250000,1.316999999)] m。主体另一可见节点的上界仅 z=0.970 m；当前开盖可见几何的上界则为 1.317 m。因此该高处碰撞坐标不是 Collision 层独自抬高出来的面，不能用旧的整体参考高度替代本轮实际开盖变换。

“开盖板/盖板顶缘”是结合已查看原 RGB 和几何位置的语义解释；USD 节点本身只有编码名称、没有规范 lid 标签。完整 [可见节点映射](visual_source_mapping.json)保存实际矩阵、AABB、近邻三角面顶点；[全部顶点对应检查](visible_collision_vertex_correspondence.json)保存双向距离和逐点比较。

该检查确认本轮可见材料与 authored 碰撞输入一致，不证明实际附着 cooked PxShape、内核碰撞时间或 raw impulse 幅值可靠；不能将其推广为全场景 cooked 几何已校准。离线 GT 点与任何标注均未送入 policy。后续确定性前缀诊断仍须独立真实执行。
