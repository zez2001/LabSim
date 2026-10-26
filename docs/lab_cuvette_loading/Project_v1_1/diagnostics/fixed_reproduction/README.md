# 原异常动作序列修复前后对比（fixed_replay_01）

两条原动作前缀均通过新连续FK执行器完成，未调用GPT。第三动作分别为world [0,+40,0] mm和[0,+35,-19] mm，原先的213.732/230.539 mm异常位移未复现。此处是确定性控制诊断，不是完整装载成功，也不是GPT成功。

**进程缺陷仍须明确保留：本次实际退出码139。** 两集及run_manifest写完、writer关闭后，Isaac扩展完成卸载，Python interpreter GC阶段segfault。原process_exit.json及退出前最后50行日志均已复制，日志确有扩展shutdown后“Garbage-collecting / no Python frame”fatal信息。数据完整性、H5可读性和物理轨迹可独立核验；不能把本轮写成进程正常退出或最终发布验证通过。

本轮使用新task/facade与旧GenericRobotTools适配符号。probes的该导入之后才修正；新ProjectV11RobotTools包装器没有由本次GPU运行验证。执行源码在工作树内，物理依赖哈希取自每集release contract，不能把后来修改的当前文件哈希冒充运行版本。

## 两条第三动作

- 序列1：请求 40.000000 mm；实际净位移 213.732126 → **39.971032 mm**；对最终目标位置误差 196.807216 → **0.228553 mm**；姿态误差 19.231924 → **0.047194°**。
  新动作实际执行120控制tick/480物理步/2.000000s；accepted、execution_finished、target_reached均true，safety_stopped及partial_execution均false。新控制端点差分峰速0.020029m/s，原值0.730915m/s。
- 序列2：请求 39.824616 mm；实际净位移 230.539316 → **39.781691 mm**；对最终目标位置误差 224.840426 → **0.064917 mm**；姿态误差 23.859877 → **0.032118°**。
  新动作实际执行120控制tick/480物理步/2.000000s；accepted、execution_finished、target_reached均true，safety_stopped及partial_execution均false。新控制端点差分峰速0.019939m/s，原值0.732212m/s。

第一序列后续wait现在也完整执行120 tick/2秒，终点位置误差0.357308 mm；旧wait仅4 tick即IK失败。第二序列第三动作由旧114 tick部分执行变为120 tick全部执行。

## 路径、连续性与数据核验

- 序列1全程最大位置跟踪误差0.357373mm、姿态误差0.048604°；最大命令关节步长0.001431779rad；seed与上次applied command最大差0rad；全部runtime_stop为空、forbidden接触标志false。
  H5关闭后只读重开：480条transition，complete=true；全部动作/关节/command/时间列有限，obs→next时间差逐条1/60s；原文件size/mtime未变。这里只检查结构和指定列，未做训练batch读取或全图像像素读取。
- 序列2全程最大位置跟踪误差0.288136mm、姿态误差0.035010°；最大命令关节步长0.001102750rad；seed与上次applied command最大差0rad；全部runtime_stop为空、forbidden接触标志false。
  H5关闭后只读重开：360条transition，complete=true；全部动作/关节/command/时间列有限，obs→next时间差逐条1/60s；原文件size/mtime未变。这里只检查结构和指定列，未做训练batch读取或全图像像素读取。

已核对原动作参数前缀逐项一致，初始TCP与legacy相同；physics、vessel、rack、scene、adapter配置及资产哈希清单相同。新执行器不再逐关节clip一个远IK解，也不把目标重定向到跑偏TCP周围10mm；每tick采用与前次applied命令连续、FK复核通过的局部解。

本轮两条第三动作满足自由空间初步1mm/0.5°门槛，但全程仍有约0.2–0.36mm跟踪误差。尚未单独验证预插入附近约0.1mm预算，不将名义FK机器误差当实际精度；也未覆盖所有±XYZ/TCP朝向、夹持物、插入接触或完整装载。

原独立判分保留CONTROL_DIAGNOSTIC_COMPLETE/POLICY_BUDGET、task_success=false；不把没有抓取/装载的探针计为完整任务失败配额或成功BC。仍保留NATIVE_TARGET_OVERLAP_UNAVAILABLE物理质量告警。

## 证据

- `action_comparison.csv`：全部7条动作的新旧结果；`tick_metrics.csv`：全部执行tick的可复核指标（缺失量留空）。
- `summary.json`：精确数值、原判分、H5检查、依赖/输入SHA及退出证明。
- 本目录复制了小型原始回执、判分和进程证明；完整H5、物理日志、视频保留在原输出，JSON中原路径仅作来源。

![连续前缀与第三动作轨迹](trajectories.png)

旧第一序列约6s处误差曲线下降，是wait以当时已跑偏的实际TCP建立了新保持参考；不表示回到了第三动作原目标。

![逐tick误差和实际速度](tracking_errors.png)

![关节步长和seed连续性](joint_continuity.png)
