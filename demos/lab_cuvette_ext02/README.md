# V0_ext02 桌面支撑与抓放诊断

本版本已验证独立支撑、物理抓取、抬升、保持和短距离搬运。最终运行在松爪前的低速门槛终止，未执行 OPEN、撤离及释放后观察，也未启动固定五次完整抓放。完整仪器装载未执行，所有 `full_success` 与 `full_task_eligible` 均为 false。不要将这些记录加入原任务的成功训练索引。

完整补充报告位于 `/home/wujing/Desktop/vla/LabSim/docs/lab_cuvette_loading/V0_ext02/`，原始诊断记录位于 `/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_ext02/`。源附件、V0 和 V0_ext01 保持原状。

## 复现已记录的最终受阻条件

在项目根目录执行。输出必须是不存在的新目录，去掉 `--headless` 可显示 GUI。启动器使用共享 GPU 锁顺序运行。

```bash
cd /home/wujing/Desktop/vla/LabSim
bash demos/lab_cuvette_ext02/run_robot.sh \
  --headless \
  --config config/lab_cuvette_loading/V0_ext02_tgs_default_velocity.yaml \
  --initial-state config/lab_cuvette_loading/V0_ext02_initial_state.json \
  --support-evidence outputs/lab_cuvette_loading/V0_ext02/support_tgs_default_velocity/walls28_mm \
  --output outputs/lab_cuvette_loading/V0_ext02/my_table_run_01

../labutopia-env/bin/python -m demos.lab_cuvette_ext02.analyze_table \
  outputs/lab_cuvette_loading/V0_ext02/my_table_run_01/trial_00
```

最终仿真执行版本为 `75a2ebb2d87a91568b94903e4bc8c0f6d8962695`；交付代码只补充失败原因标签和独立分析。旧原始结果名 `PLACEMENT_SUPPORT_NOT_ESTABLISHED` 表示复合条件失败，不表示完全没有桌面接触。交付代码在已有支撑但速度未通过时打印 `PRE_RELEASE_UNSTABLE`。原始动作、结果文件和验收阈值没有据此改写。

## 重新运行独立支撑及几何核查

```bash
cd /home/wujing/Desktop/vla/LabSim
bash demos/lab_cuvette_ext02/run_support.sh \
  --headless \
  --config config/lab_cuvette_loading/V0_ext02_tgs_default_velocity.yaml \
  --schemes walls28_mm \
  --output outputs/lab_cuvette_loading/V0_ext02/my_support_run_01

../labutopia-env/bin/python -m demos.lab_cuvette_ext02.audit \
  outputs/lab_cuvette_loading/V0_ext02/my_support_run_01/walls28_mm
```

机器人运行需要同时通过静置与支撑几何门槛，并核对原生射线与支撑证据。使用新支撑结果时，把 `--support-evidence` 改为上述新目录。`--hz 480` 可用于单独步长诊断，控制仍为 60 Hz；本轮未获得严格配对的步长收敛结论。

## 证据与限制

- 28 块厚壁资产的世界尺寸与源视觉网格保持一致；局部毫米坐标由逆向 prim 缩放抵消。支撑区域已观察到的查询几何误差为 0.009516 mm，不能称为全局上界或真实标定精度。
- 独立静置末三秒未观察到源网格穿透；最初下落仍记录到约 1.13123 mm 瞬态穿入。不能宣称全过程穿透已经解决。
- 烹饪查询表示记作 Cq，与实际原生表示 C 区分。旧 193 凸体的 Cq 与原生射线仍不一致，不能把旧 0.312 mm 直接认定为完整原生碰撞误差。
- CPU 下 SDF 标签资产实际使用 TriangleMesh 回退，未验证 GPU SDF。该 CPU 对照在机械臂加载时出现源面穿透，未选作抓放方案。
- 最终放置阶段位姿漂移很小，但原生速度门槛未通过；其与位姿差分的不一致仍待解释。没有通过替换测量口径、放宽门槛或强制松爪制造成功。
- 两候选目标座身份、配套关系、实际插入方向和限制净宽尚待确认。来源架仍是 V0 代理，高敏感孔配合与扰动范围均未放行。

`independent_tabletop_score.json` 区分支撑、抓取、保持、搬运和释放稳定，保留 `OPEN_executed`。CSV、H5、实际物理步、接触点及冲量、源码快照和有效参数均保存在各轮目录。未测量的完整装载深度与体积相交不补零。
