# V0_demo04 独立12.5mm器皿派生

从V0_ext02/walls28_mm.usda实际视觉材料网格与28块厚壁碰撞输入派生；所有点使用同一刚体局部仿射变换diag(12.5/14.85,12.5/14.85,1)。XY缩放，高度、底部Z=0、拓扑和全部原碰撞/材质参数不变，不对局部壁形作让位。这是经授权的新假设器皿，不能写成原CAD已修正或真实型号配套。

质量继续设为20g（工程假设）。对闭合、定向的实际视觉材料边界进行有符号四面体体积积分，包括底部和内腔壁；同质材料分布假设不变。总质量固定，因此缩放后数值密度相应增大，不是同种材料实测密度。计算COM、完整惯量张量、主轴和主惯量；另由源中心二阶矩Q进行完整仿射Q'=SQSᵀ与I'=m(tr(Q')Id−Q')验证，没有套用等比缩放s²规则。用trimesh表面积分独立核对，并重载USD属性重建完整张量。

尺寸来自实际顶点和完整局部变换；12.5mm是按源名义14.85mm定义的比例，源float顶点使实际包络略有数纳米舍入差异，不能当作真实精度。sections.csv覆盖底部、过渡、直壁和杯口13个实际高度。蓝线为实际视觉材料截面，橙线为28个碰撞输入点的数学凸包截面（含内部切分边，仅作调试显示）。CSV报告其几何并集的包络宽度；没有按内部切分边计算外表面误差，也没有相加重叠面积冒充实体体积。面积、覆盖误差及穿透未在此测量。这是输入几何检查，不是PhysX实际烹饪表示读取；未启动Isaac/GPU。

产物：derivation.json、mass_properties.csv、sections.csv、visual_collision_overlay.png、material_sections.png。源文件SHA保持70133b2a66b1705f6de80c52e46c857b02a9811386971ea14b6a188e1edfde4b。原座配合由独立geometry gate判断，本文件不标注任务成功。

复现（要求新目标文件与新证据目录）：

```bash
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo04.build_vessel --output outputs/lab_cuvette_loading/V0_demo04/vessel_check/vessel_125_mm.usda --evidence outputs/lab_cuvette_loading/V0_demo04/vessel_check/evidence
```

## 独立重载及复建复核

`mesh_dimensions.csv`另逐形状列出前后实际包络，包含整体视觉与碰撞输入并集包络。`independent_reload_check.json`实际比较942项非预期修改属性与88项材质绑定等关系，均保持；COM和主惯量为有意重算项。`rebuild_check.json`记录在另一个新目标完整复建，USD逐字节SHA一致；已有目标拒绝覆盖，原文件与证据未改变。所有工作均为CPU离线USD/网格检查。
