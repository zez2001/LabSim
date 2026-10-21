# Size_v1 原座固定、器皿横向尺寸假设

资产入口为 `assets/lab_cuvette_loading/Size_v1/registry.json`，以 `asset_id`
选择独立USD；原12.5mm文件和原A座不写回。选定初始物理候选
`cuvette_xy_1000`（10.00×10.00×67.5mm，20g假设），目标原A座局部
XY偏移(+0.650,+0.001)mm，杯底候选Z=2mm、插入深度约27mm。

所有候选共用同一规则diag(width/12.5,width/12.5,1)，包括视觉和28块厚壁
碰撞输入。材质、碰撞参数、拓扑、原点及高度不变；不会制作局部避让。
质量保持20g并对实际闭合视觉材料体积分COM/惯量，数值密度相应改变，
不是物理材质或真实质量校准。每个独立USD重载核查，并保留源和产物哈希。

离线生成（无需Isaac进程或GPU）：

```bash
bash demos/lab_cuvette_external/usd_python.sh \
  -m demos.lab_cuvette_size_v1.build_assets --widths-mm 12.5 11.0 10.5 10.0 9.5
```

完整家族扫描（输出目录须不存在，保留所有评估尺寸）：

```bash
bash demos/lab_cuvette_external/usd_python.sh \
  -m demos.lab_cuvette_size_v1.scan_family \
  --config config/lab_cuvette_loading/Size_v1/standard.yaml \
  --output outputs/lab_cuvette_loading/Size_v1/new_geometry_scan \
  --geometry-site /home/wujing/Desktop/vla/physicalrsi-runtime/sim-env/lib/python3.11/site-packages
```

当前35个已保存资产覆盖9.50–12.50mm。入口必要截面检查的四个直立方位
均遍历全部有界XY域，观察到11.00mm仍有正间隙域、11.02mm起无域。
保守全深竖直扫掠正证书最大已观察尺寸10.70mm；10.72–11.00mm属于入口
可行但保守全深未认证，不写成全局不可通过。10.00mm固定偏移的侧向输入
表面保守余量约0.350mm，静态采样支撑凸包包含按真实材料体积分的COM。

正几何证书不是物理接触、释放稳定或完整任务成功；没有读取PhysX实际烹饪
形状或证明任意倾斜6DoF路线。几何证据见
`docs/lab_cuvette_loading/Size_v1/geometry/family_20261021_02/`。
