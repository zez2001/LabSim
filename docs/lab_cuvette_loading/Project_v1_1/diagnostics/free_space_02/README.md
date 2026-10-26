# free_space_02 已完成覆盖与补测清单

实际进程已关闭，session76988，exit0。原判分为SIMULATION_TIMEOUT/TIMEOUT，实际仿真170.000000s、10199个控制tick、40800个物理步（含4步初始化）。process_exit.json注释写180s，与原结果和时间记录不符；本派生分析使用170s，不修改原证明。

**72/72个方向探针全部完成，最后超时的不是TCP40mm方向探针。** 覆盖为pose0的world、pose1的world和TCP三组，每组均包含1/5/20/40mm、±X/±Y/±Z，共24项；72项accepted/target_reached=true、各自执行全时长，无方向探针partial。逐项与分组见`signed_probes.csv`、`group_coverage.csv`。

仅需补齐：

- pose1最后返锚动作：第162号请求1.666667s/100tick，实际只执行4tick/0.066667s，任务总时限到达；剩余原参考约1.6s。须使用新观测建立安全新路径，不能把它当作完全未执行而重放。
- pose1返锚后的wait1s。
- pose1夹爪开口0.06m与0.08m各1s、effort5N。

pose0的wait及两次夹爪动作已完成；进入pose1的+Z30mm和world旋转向量[0,0,0.1]rad也已完成。最后一个pose1 TCP-Z40mm方向探针是第161号，已完整161tick/2.683333s；之后才进入超时的返锚动作。无需为覆盖再运行全部72项。

## 实际误差和保持范围

72项单次终点位置误差median/P95/max为0.415474/0.665032/0.673394mm；姿态误差对应为0.046678/0.062282/0.062619°。全程控制边界采样最大跟踪误差0.673516mm/0.064893°，TCP差分速度最大0.017720m/s。没有runtime_stop或记录的forbidden robot/environment接触。采样最大值不是物理子步或连续时间最大值。

单次均在自由空间初步1mm/0.5°门槛内，但不支持约0.1mm精细插入预算。尤其不能将每次小姿态误差等同全程姿态保持：相对各pose最初anchor，pose0末累计旋转2.534063°，pose1末累计4.901843°。

源码中的返锚只恢复XYZ，每条后续零旋转增量又以当时实测R建立新目标。这个调度并未固定anchor的四元数，因此局部偏差会被下一动作继承；本证据不说明单次world/TCP旋转组合错误，也没有单独解释驱动残差来源。下一步可用显式完整ee_pose(anchor位置+四元数)做姿态保持/返锚诊断，先不悄悄改变ee_delta参照语义。原free02实际轨迹保持原样。

pose0已执行的1s wait：相对起点最大/终点位置漂移0.395510/0.395510mm，姿态最大/终点变化0.045071/0.045071°。单次hold与跨动作累计旋转分别记录。

![单次终点误差](endpoint_errors.png)

![累计姿态与实际速度](orientation_and_speed.png)

## 超时及旧调度问题的分类

第162号partial回执的stop_domain为task，stop_reason为SIMULATION_TIMEOUT，原独立结果record_valid/record_integrity_valid/physics_trustworthy均true。旧wrapper同时保存了SIMULATION_STATE_STOPPED错误，这是包装层误分类；新wrapper已单独修正并CPU测试，原数据不重写。总时间上限不是数值失稳，不把该partial的23.93mm“对最终目标距离”当成完整动作终点精度失败。

free_space_01另行保留：在完成13个带定义的方向探针后，返锚请求约20mm却只给0.3s，PROTOCOL_TRANSLATION_SPEED_LIMIT正确拒绝，未产生新回执、TCP相对前一动作终点变化0.000000mm。它属于探针调度/协议问题，不是物理精度失败，也不与free02合并增加覆盖数。

本分析只CPU读取关闭后的JSON/JSONL，没有打开H5、跑GPU或调用模型；源记录未修改。原判分和小型退出证明随附；完整动作、配置、源SHA与统计口径在summary.json，163条动作（含返锚及辅助动作）在all_actions.csv。诊断没有执行完整抓取/插入，不计完整任务成功或失败配额。
