# 通用接触保持 A/B：grasp_transport_01 与 02

日期：2026-10-27。A为已闭合的旧generic latch诊断（session34718、exit0），B为新no-reopen接触保持诊断（session68180、exit0）。这是固定场景的确定性诊断对照，不是GPT、训练或完整装载验证。

![开口、力、相对滑移及真实物体短移对照](contact_hold_AB.png)

## 核实结果

两集保存的配置内容完全相同；共同请求的前16条工具名及参数逐项一致，仅排除必然不同的episode/observation身份。相机配置、初始场景、名义接近轨迹、3秒闭合时序及力上限不变；夹持阶段均为每指5 N，之前初始化/接近的8 N默认值也相同。A完成15条区间，第16条短移只执行0.766667 s后停止；B完成计划中的17条区间，包括完整短移和最后2秒保持。

物理记录的首个应用目标差异出现在21.220833 s（21.216667 s控制分派后的第一physics sample）：A从9.394444 mm放宽至10.460504 mm，B保持9.394444 mm。两条记录在此之前相同的逻辑请求仍是9 mm。B没有通过增加force cap、修改摩擦、质量、尺寸或任务门限解决失握。

27.233333–29.233333 s等待窗口，A双指平均力[0.160175,0.161029] N，B为[1.216594,1.217245] N。A的原接触门控锚点轴向漂移达到26.866891 mm；B最大0.000795929 mm。B原独立底部相对漂移最大1.819 µm、锚点总相对漂移0.813 µm，均是该仿真中的相对保持量，不能解释为真实平台精度或标定精度。图中inset仅放大B的相对量，未放宽原0.2 mm/1°成功判据。

独立source-clear事件：A为23.950000 s，B为23.287500 s。A在29.929167 s两指力同时变为0，随后29.995833 s物体单步位移超过原3 mm守卫并在30.0 s闭合；保留原SIMULATION_FAILURE与task_success=null。该路径的上游滑移不会因后段守卫而从分析中消失。

## 短移用实际物体位移核对

两集请求相同world delta=[20,0,20] mm，名义范数28.284271 mm，时长2秒。B在29.233333–31.233333 s的实际物体位移为 **[19.658864,0.327885,19.665420] mm，范数27.808401 mm**；它不只是TCP移动，物体随夹爪完成了这个短移。该动作TCP回执target_reached=true、完整消费2秒，之后再完成2秒保持。

A对应动作在0.766667 s后中止，物体Δ=[8.136608,3.019154,−31.134009] mm。其32.320987 mm位移范数包含向下滑落，不能据此说完成了更长搬运。右下图按world Δx/Δz画轨迹，避免将掉落距离与短移完成混为一谈。

## 评分与数据边界

B原grasp_success=true、record_integrity_valid=true、physics_trustworthy=true；完整结果保留CONTROL_DIAGNOSTIC_COMPLETE / POLICY_BUDGET、task_success=false。A记录完整性true而物理可信度false，说明两轴未合并。两集condition_group均为control_diagnostic、success_bc_eligible=false，正常完整任务ACT/DP reader不接收这些记录为BC样本。

**完整装载在两集中都没有执行。** B虽然完成短移，原transport_success仍为false，measured_grasp_segments.transport.status仍为unavailable；它没有触发原完整任务的held-transport门槛，也没有插入、支撑交接、释放、撤离和撤离后稳定验证。不能称B完整任务成功，也不把原false/null字段改写。

## 读取方法与证据

开口和力使用240 Hz实际physics rows。锚点为配置的器皿body点[0,0,53 mm]，沿首次独立抓持参考中的器皿轴投影；漂移曲线使用原scorer的接触>=0.01 N门控。generic hold自身仍使用既有0.03 N/0.1 s参数。逐时CSV按完整控制边界抽取，最大值和事件时间由全部physics样本计算。

- [关键指标对照表CSV](comparison_metrics.csv)；[逐时控制边界CSV](time_aligned_control_samples.csv)。
- [原字段和重算摘要](summary.json)；[逐条动作意图比较](action_intents_comparison.json)。
- [PNG图](contact_hold_AB.png)及[矢量SVG](contact_hold_AB.svg)。
- [原MP4直接提取帧及实际模拟采样时刻](video_frame_manifest.json)；[源H5/评分/配置/视频SHA](source_hashes.json)。
- 每run的closed_read_archive JSON记录H5全量分块读取、原非raw文件哈希保护与无损gzip证明；[三run归档摘要](archive_summary.json)另包含pose_hold_01的闭合CPU读审计。它仅做文件资格与可恢复性校验，不把pose-hold解释为完整装载。

本次图表是两个确定性运行之间的回归证据，尚不构成随机化成功率或所有姿态/物体的泛化结果。这份离线分析仅使用CPU读取已闭合run，未另启动GPU/API，也未重写历史评分。

三集H5全部唯一dataset对象均已分块读过，动作/状态有限值、8D映射、双相机hardlink和相邻时间检查通过。无损归档共节省851,669,863字节；三个run共166个原非raw文件的SHA保持不变。每集两份raw日志均逐字节解压SHA核对后才删除原文件，H5、评分、录像和process-exit证据均保持原样。

B的[真实helper状态事件](hold_state_events.json)显示21.216667 s首次冻结、21.316667 s连续窗口确认，候选保持10.460504 mm但应用值持续9.394444 mm。

补充：[接触前实际状态逐时比较](pre_latch_measured_prefix_comparison.json)核对至21.216667 s共5093个physics样本，所列TCP、器皿、双指力/位置、关节命令及effort值全部逐值完全相同；首个应用目标分歧发生于其后21.220833 s。
