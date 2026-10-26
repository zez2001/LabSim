# grasp_transport_01：通用接触保持离线诊断

分析日期：2026-10-27。对象为已闭合的 `Project_v1_1/grasp_transport_01`（真实 session 34718、exit 0），以及历史 Project_v1 `teacher_gui_01` 的成功轨迹。本文件没有修改任务、旧评分、H5、物理参数或成功阈值，也不是 GPT 演示或新的物理成功结论。

## 结论

可直接定位的实现问题是 **接触 latch 放宽了已经应用的闭合目标**。在 t=21.216667 s，双指接触已出现，generic 路径从实测宽度重新推算 latch，将上一目标 **9.394444 mm 改为10.460504 mm**，一次放宽 **1.066060 mm**。逻辑请求始终是9 mm，每指驱动上限始终为5 N。逻辑请求、分派 ramp、应用目标和实测开口在这里不能混称“请求开口”。

本次证据不支持“lift开始后立即零接触”或“只有一个虚假双指脉冲”的表述。240 Hz 原始记录中，两指力均>0.03 N从21.204167 s持续至29.920833 s；提取和等待期间仍有约每指0.16–0.20 N，但发生明显相对滑移。两指同时零力从29.929167 s开始，首个超过既有3 mm单步门限的物体位移在29.995833 s出现，晚66.7 ms。更准确的顺序是：目标放宽、低力保持且滑移、失去接触、后段触发跳变守卫。

这条时间链足以把上游抓持问题和后段守卫分开，但尚不能证明 latch 放宽是全部滑移的唯一原因。历史 teacher 的上限为8 N、闭合/接近时序与控制器也不同，不能把历史成功当作同条件因果对照。

## 对齐证据

- 21.200000 s前状态：应用9.788888 mm；本 tick分派9.394444 mm，之后实测10.770723 mm、双指力[0.988321,1.767882] N。
- 21.216667 s：原始逻辑9 mm、分派 ramp已到9 mm；weight-based候选10.460504 mm覆盖了上一已应用9.394444 mm。下一状态力降为[0.211923,0.407626] N。
- 21.250000 s之后短时力进一步降至约[0.069183,0.105984] N。应用目标随后保持10.460504 mm，实测开口逐渐收敛至约10.621 mm，不能用跳变之后的约10.50 mm代表整个lift。
- 21.691667–23.950000 s提取窗口：平均双指力[0.167215,0.197871] N；27.233333–29.233333 s等待窗口为[0.160175,0.161029] N，双指接触仍在。
- 原独立 scorer的接触有效范围内，底部相对漂移27.001528 mm，配置抓持锚点的轴向漂移26.866891 mm；本离线重算与原值一致。锚点沿参考器皿轴投影，底部坐标还含旋转杠杆效应，二者不能混用。
- 29.995833 s的实际物体单步平移为3.055945 mm，触发原守卫；记录在30.0 s终止。保留原 `SIMULATION_FAILURE`、`task_success=null`、`physics_trustworthy=false`；`source_slot_cleared=true`不能提升为稳定抓持或搬运成功。

generic/teacher接触保持阈值均为原配置0.03 N。独立 scorer的参考和漂移更新仍使用其原有>=0.01 N条件；这里重算仅复现相同条件，没有调整任何门限。JSON内全行后失触漂移与接触门控漂移分别标明，不能将后失触分析值写回历史评分。

## 与历史成功 teacher 比较

Teacher在14.550000 s首次双指接触时立即冻结上一闭合命令9.666667 mm；持续接触窗口后，14.666667 s确认 latch，继续使用9.666667 mm。它没有采用当时会放宽到10.308448 mm的weight-based候选。静态保持平均力约[0.920038,0.973567] N，提取窗口约[0.946484,0.947084] N，实测总开口约10.619 mm。

配置中相同的 `latch_transition_policy=preserve_first_contact_command` 和 `contact_persist_s=0.1` 并未使旧父 task 的 generic 分支使用 teacher的这个状态机：generic只在首个控制边界看到bilateral便直接用测量候选锁定，既没有持续确认，也没有“不得宽于上一命令”的约束。成功 teacher的实现另在controller内，首次接触先冻结，连续0.1 s后确认；丢接触时按已有慢闭速度恢复。

两者闭合前的实际TCP位置差0.227737 mm、姿态测地角差0.256845°。这是这两条仿真轨迹的状态差，不是平台精度或真实标定结论。历史 teacher的独立评分为完整SUCCESS，底部相对保持量最大4.902 µm；同样仅是该仿真记录的指标，不外推为真实微米级操作能力。

## 建议与已实现的最小 helper

新增纯 CPU `GenericContactHold`，输入仅为原逻辑请求、分派 ramp、上一应用目标、手指位置/力、模拟时间及既有质量/friction/kp/compression/threshold/persistence/慢闭配置。没有物体姿态、teacher阶段或自动任务宏入口，也不修改force cap。

1. 首次bilateral即冻结 `min(previous_applied, measured_sum-2*weight_compression)`（保持已有最小开口边界），绝不把已应用9.394444 mm放宽到10.460504 mm。
2. 按原0.1 s连续窗口标confirmed；此前或持物中失触，只以原0.002 m/s向原逻辑goal慢闭，不能跳到已经过去的ramp终点。
3. 显式变宽解除freeze，并完成原开启ramp，避免仍有瞬时接触时重新锁住；同一逻辑请求的move/wait沿用已应用目标。
4. 保留原3 s、180 control tick的无接触闭合时序。每tick记录原逻辑、分派、应用、实测、candidate、confirmed和recovery；不因新的“confirmed”字段修改独立任务成功谓词。

18项CPU状态测试覆盖上述实际反例和状态边界，均通过。下一次真实对照应只改变该保持实现，保持相同接近/闭合/lift/wait/短transport前缀、5 N上限、初始姿态、场景、阈值和物理参数。先核对连续接触、原有相对漂移判据及跳变守卫，再决定是否进行完整任务。本文不预先宣称 helper已通过真实抓持，更不通过放宽pose-jump阈值掩盖上游失握。

## 附件与来源

[完整数值摘要](grasp_transport_01_latch_evidence/analysis.json)、[H5逐步接触转换](grasp_transport_01_latch_evidence/h5_latch_transition.json)、[对齐样本CSV](grasp_transport_01_latch_evidence/aligned_samples.csv)、[源文件SHA](grasp_transport_01_latch_evidence/source_hashes.json)、[视频实际采样时刻](grasp_transport_01_latch_evidence/frame_manifest.json)。H5按r模式读取；这些诊断记录不进入BC数据。

已逐帧检查6张原MP4直接提取帧：新轨迹21.25 /27.25 /29.95 /30.0 s，历史teacher14.683333 /22.416667 s。新轨迹后段可见器皿相对夹爪向下移动；图像不用于替代力或漂移数值证据。旧/新腕相机视图不同，不能跨画面像素位置推断物体位姿差。

![新轨迹闭合后21.25秒](grasp_transport_01_latch_evidence/new_0637.png)

![新轨迹失触后29.95秒](grasp_transport_01_latch_evidence/new_0898.png)

![历史teacher确认保持后14.683秒](grasp_transport_01_latch_evidence/teacher_0440.png)
