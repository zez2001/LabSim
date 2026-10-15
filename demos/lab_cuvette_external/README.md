# lab_cuvette_loading V0_ext01 外部资产接入

独立分支 `codex/lab-cuvette-external-assets`。原 V0 代码、资产、配置及历史输出不改动。
这是外部资产接入原型，`calibrated=false`，不是实际器材校准版。

## 当前验收边界

- 包内仪器和独立器皿均已接入视觉与碰撞；没有保留隐藏的 V0 装载座。
- 来源架继续使用 **V0 参数化代理，未替换**。机器人仍为旧 Franka；桌面为合成代理，本版为容纳更大仪器扩大到1.6×1.5m，未缩放源仪器。
- 两个候选座身份未确认。在声明的直立、居中、竖直下降姿态下，实际网格截面存在干涉。
- 新器皿配旧15mm架孔只有约75微米单侧名义余量。实际支撑发生抖动，未通过初态验收。
- 已做落稳、侧壁、夹持保持和释放诊断；桌面夹持保持子阶段成立，释放后倾倒，整条诊断失败。
- 凸分块已导出并读回烹饪表示，但其抽样偏差和源视觉几何对桌面约0.28mm越界，尚不能支撑窄余量接触验收。
- `task/standard/random` 是**明确输出受阻状态的关口**，没有运行完整装载或10/20次批次，也没有完整任务成功数据。

## 已实现的入口

在 `/home/wujing/Desktop/vla/LabSim` 执行。`run.sh` 使用现有 `../labutopia-env/bin/python`，并以 `flock` 串行化本版本仿真进程；不停止其他用户进程。每次输出必须是新目录，省略 `--output` 则使用新时间戳。

```bash
# GUI查看外部资产，保留窗口；不是完整装载任务
bash demos/lab_cuvette_external/run.sh --mode scene --debug-material --keep-open

# 独立USD读取和实际顶点尺寸检查，不启动Isaac
bash demos/lab_cuvette_external/usd_python.sh demos/lab_cuvette_external/validate_assets.py

# 实际网格截面及声明姿态的配合分析，不运行物理
bash demos/lab_cuvette_external/usd_python.sh demos/lab_cuvette_external/feasibility.py

# 最小物理诊断，逐条顺序运行
bash demos/lab_cuvette_external/run.sh --mode physics --test drop --headless
bash demos/lab_cuvette_external/run.sh --mode physics --test side --headless
bash demos/lab_cuvette_external/run.sh --mode physics --test rack --headless
bash demos/lab_cuvette_external/run.sh --mode physics --test grasp --headless
bash demos/lab_cuvette_external/run.sh --mode physics --test grasp_table --headless

# 实际执行过的完整任务/批次关口：返回blocked，无完整仿真批次
bash demos/lab_cuvette_external/run.sh --mode task
bash demos/lab_cuvette_external/run.sh --mode standard
bash demos/lab_cuvette_external/run.sh --mode random

# 已保存诊断数据的独立状态与时序审计
bash demos/lab_cuvette_external/usd_python.sh demos/lab_cuvette_external/audit.py

# V0所有受保护文件与原始来源内容重新计算SHA256
bash demos/lab_cuvette_external/usd_python.sh demos/lab_cuvette_external/verify_baseline.py
```

派生资产生成入口为：

```bash
bash demos/lab_cuvette_external/usd_python.sh demos/lab_cuvette_external/build.py
```

该命令已经运行，默认目标 `assets/lab_cuvette_loading/V0_ext01/derived` 存在时会拒绝覆盖。
正常查看及测试直接复用已交付派生资产。可在全新缓存路径验证重新生成（已执行同类命令）：

```bash
bash demos/lab_cuvette_external/usd_python.sh demos/lab_cuvette_external/build.py \
  --output outputs/lab_cuvette_loading/V0_ext01/rebuild_NEW
```

重建资产的元数据写在该缓存的metadata目录；它不会自动切换运行资产。若要试用另一个派生目录，应显式创建新配置并修改derived_directory；不覆盖现有版本。

## 文件与追溯

- `assets/lab_cuvette_loading/V0_ext01/source/`：原压缩包和逐文件只读副本；包内脚本未执行。
- `assets/lab_cuvette_loading/V0_ext01/derived/`：标准化视觉、动态器皿、静态仪器和独立复制的V0架。
- 同级 `derived_initial_vhacd/`、`derived_radial_default_thickness/`：保留碰撞表示排查过程，不作为最终入口。
- `config/lab_cuvette_loading/V0_ext01.yaml`：显式选择来源、派生资产、安装变换、物理及关口。
- `docs/lab_cuvette_loading/V0_ext01/`：基线、来源、变换、尺寸、截面、物理读回说明、审计及结果报告。
- `outputs/lab_cuvette_loading/V0_ext01/`：每次新输出；带配置、源码快照与SHA256、git/dirty、初态、实际状态、H5、双视角MP4及终止原因。

## 记录接口

继续使用原 `LabCuvetteLoadingCollector`/`MinimalPickCollector` 的H5写入；新子类只补充“重叠不可用”字段并改写诊断视频标签。
学习观测仍为双RGB CHW uint8 256×256和8维状态；动作为7关节绝对位置rad加单指对称开度m；实际机器人状态9维。
每个60Hz控制动作保持4个240Hz物理步，`obs_t → action_t → next_state`。本版诊断的 `privileged/progress` 只有 `actual_held` 一列，附加可用性布尔字段；不是原完整任务八阶段的完成标记。

所有本轮诊断的H5 `success=false`、`full_task_eligible=false`；成功的落稳检查不等于完整装载成功。没有把诊断混入V0或完整任务训练索引。
`privileged/overlap_m=0` 是兼容旧写入器的占位，必须同时检查 `overlap_measurement_available=false`，**不能解释为零穿透**。视频明确写 `mesh overlap NOT measured`。
独立审计另用源网格全部顶点和实际姿态计算水平桌面越界，并报告覆盖局限。未声称沿用旧Box/SAT即可排除新Mesh穿透。

后续ACT/DP可沿用学习字段的形状语义，但当前没有合格完整成功轨迹；现有适配器应拒绝这些诊断文件，不能为了读取batch而把它们改成成功。

## 控制和判分

`grasp_table` 是桌面局部夹持诊断，来源不是旧架槽；不能混入完整来源架任务。
初态仅在录制t=0前设置并清零速度；侧壁诊断可设置初始0.4m/s水平速度。录制后没有设置器皿位姿、固定约束或吸附。
夹持诊断先静置2秒，检查最后1秒速度；再接近、保持、闭合、提起、保持、短距离搬运、打开与观察释放。
靠近后实际TCP未到2mm范围则停止；双指实际接触均大于0.02N、实际抬升40mm并保持1秒才记为夹持保持子阶段成立。
原V0的18mm装载深度等判据没有用于新仪器；新完整任务阈值仍为null，等待身份、几何和碰撞关口通过后制定。

落稳“通过”只表示当前诊断的接触、速度和原点高度屏查；不代表源网格无穿透或碰撞精度通过。独立审计已发现约0.28mm桌面越界，窄配合不得据此验收。
