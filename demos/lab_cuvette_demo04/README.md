# V0_demo04 单仪器与用户名义尺寸核查

当前结论：12.5 mm 派生器皿已接入单台仪器与完整6×6架；原A/B座顶部内伸结构仍与器皿材料相交。默认完整任务在启动Isaac前返回 `GEOMETRY_BLOCKED_NOT_EXECUTED`。受限诊断只执行架内取物、搬运、座口上方停止和上抬；不等于装载、释放或完整任务成功。固定5次及随机10次尚未启动。

器皿仅XY按12.5/14.85缩放，Z与67.5 mm高度保留，视觉和28块厚壁碰撞输入同步派生；20 g为假设，COM及完整惯量重算。原12.6 mm座、凸起、另一座与CAD附件均保留，未使用16 mm适配座。仪器根节点yaw135°来自开口到架中心方向；架yaw−45°。控制使用物体真值，器皿在初始化之后始终为动态刚体，通过实际接触运动。

从仓库根目录执行，下列输出目录必须不存在，每次换新名称。共享GPU时顺序运行；任务脚本使用 `flock`，规划/静态检查也须等待已有Isaac进程结束。

```bash
cd /home/wujing/Desktop/vla/LabSim
export LABSIM_PY=/home/wujing/Desktop/vla/labutopia-env/bin/python

# 默认完整任务：当前应记录几何阻塞，不启动物理
bash demos/lab_cuvette_demo04/run.sh --headless --output outputs/lab_cuvette_loading/V0_demo04/repro_native_gate_01

# 静态加载、reset、数量与朝向检查：0个任务物理步
bash demos/lab_cuvette_demo04/run.sh --headless --scene-only --output outputs/lab_cuvette_loading/V0_demo04/repro_static_01

# 整臂非插入路径的零物理步IK/FK及输入网格碰撞检查
ACCEPT_EULA=Y "$LABSIM_PY" demos/lab_cuvette_demo04/plan_arm.py --output outputs/lab_cuvette_loading/V0_demo04/repro_plan_01

# 有界物理诊断：最低杯底停在原座最高点上方1 mm，再上抬10 mm
"$LABSIM_PY" demos/lab_cuvette_demo04/execute.py --output outputs/lab_cuvette_loading/V0_demo04/repro_diagnostic_01 -- --headless --preinsert-diagnostic --arm-plan outputs/lab_cuvette_loading/V0_demo04/repro_plan_01/arm_plan.json --initial-state outputs/lab_cuvette_loading/V0_demo04/repro_plan_01/selected_initial_state.json

# 完整复制一个已关闭的实际episode，保留失败标签，核验现有读取器
"$LABSIM_PY" -m demos.lab_cuvette_demo04.portable_episode --episode outputs/lab_cuvette_loading/V0_demo04/repro_diagnostic_01/run/trial_00 --output outputs/lab_cuvette_loading/V0_demo04/repro_portable_01
```

移除 `--headless` 可显示GUI。规划与运行必须使用同一配置文件哈希。CPU PhysX/TGS基线240 Hz，控制60 Hz，每控制周期4个物理步。没有频率扫描或训练。运行时 `runtime.json` 保存可读回的质量、增益、力限制、限速与后端；烹饪顶点和原生offset未完整读回，标记未知。双指8 N上限不是器皿重量或底部承托力；接触冲量按当前physics_dt换算。

离线资产/几何可重建到新目录，不覆盖交付资产：

```bash
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo04.build_vessel --output outputs/lab_cuvette_loading/V0_demo04/rebuild_vessel_01.usda --evidence outputs/lab_cuvette_loading/V0_demo04/rebuild_vessel_01_evidence
bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo04.native_fit_audit --output outputs/lab_cuvette_loading/V0_demo04/recheck_fit_01 --section-step-mm 0.05 --path-step-mm 0.25
```

`physics_records.json` 每物理步记录原生/差分速度、姿态、接触、命令及阶段；H5按控制步对齐obs/action/next_obs。动作8维为7臂关节rad+左指目标m，两指完整9维命令和逐步effort另存辅助流。`post_retreat_window` 在未完成释放撤离时不可用，稳定值为null；末段只能称terminal_window。原座穿透未完整测量，不能补零。

失败episode可通过显式诊断读取复用现有getitem/collate；正常成功过滤器应拒绝。导出不会修改success、native_pair_success、data_eligible或real_calibrated。阅读包内的完整H5是真实失败/受限诊断数据，不是完整成功示范；不加入原任务成功训练索引。

报告与证据见 `docs/lab_cuvette_loading/V0_demo04/report.md`。原版本、旧输出与源CAD不回写；完整原座任务需要先核实内伸结构的真实功能、刚柔性及局部配合轮廓。
