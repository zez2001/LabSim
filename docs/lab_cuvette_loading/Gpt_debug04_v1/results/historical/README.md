# gpt_debug_04 历史轨迹离线量化

本目录是同一条历史记录的新分析，没有启动模型、GPU仿真或训练。原始目录为
`outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_04/episode_0000`，episode为
`28bd2fc2-7bd7-44ee-9fb6-aaff53cbc99d`。原实际运行源码为
`63410bf9258ba2f9bd0af4d517194523fca6617c`，原环境身份为
`Project_v1_1 / standard`，不是新生成的发布版正式评测集。

先读 [historical_quantification.json](historical_quantification.json) 或
[stages.csv](stages.csv)，再检查 [原评分](original_result.json)、
[闭合审计](source_closed_audit.json)、[事件重放](event_replay.json)和
[独立漂移复算](independent_drift.json)。全部小文件与来源SHA见
[source_binding.json](source_binding.json)。

原记录仿真时长114.716667秒、6,882个控制步、27,533个物理样本。
原结果为 `task_success=false / GRASP_SLIP / POLICY_FINISH_REQUEST`，
`record_valid=true`、成功BC资格false。末尾没有实际撤离，原
`post_retreat_window` 为unavailable且稳定结果null。记录闭合与任务失败分开保留。

Progress v1.2沿原任务配置回读，历史首次确认如下：

- 有效抓持与抓取接近：14.112500秒；抓持首次候选为14.012500秒。
- 完全离架：15.562500秒。
- 持物横移50 mm：32.508333秒，来自原独立scorer物理事件。
- 到达固定预插入参考区域：66.850000秒，来自Progress固定3 mm参考距离门控。
- 对准、有效插入、目标承托、实际脱指、撤离与连续稳定均未确认。

到达预插入参考区域与原scorer的更严格 `safe_preinsert_observed` 定义分别保留。
前者没有证明横向0.1 mm、倾角0.15°与方位角0.2°的原对准条件同时成立。
目标操作区有2,436个适用控制端点，69.683333至110.266667秒。
其中横向误差均值1.094576 mm、最小0.574452 mm；倾角均值约7.400761°。
各维最小值发生时刻不同，不能拼成一个不存在的最佳位姿。

有效插入进度最大为0，有效插入深度与释放后稳定时长为N/A。旧原始投影
`insert.continuous` 与新 `effective_continuous` 分列保留，没有用来源端的
正投影冒充插入。各阶段完整连续量极值及时间见CSV，原逐步值见工程输出。

新Progress识别2次物理尝试、1次重试；原scorer的 `retry_count=0` 保持原值：

- 尝试1始于14.012500秒，110.270833秒因无支撑抓持丢失结束。固定在手参考
  下，全操作最大相对平移29.667580 mm、转角0.296824 rad。它尚未获得目标承托，
  因而“全操作”和“首次目标承托前”区间相同；抓持质量为false的样本也计入。
- 尝试2始于111.020833秒，111.475000秒重新确认抓持；114.716667秒主动结束，
  outcome为incomplete。其新固定参考下最大平移0.341537 mm、转角0.008302 rad。
- 支撑交接区间从未发生，保留N/A。第一次抓持质量不满足发生于控制端点71.9秒，
  不能与110.270833秒确认的连续无支撑接触丢失混为一个时间定义。

独立事件重放消费全部49条事件，包括第49条finalize事件；attempt、retry和
最终outcome均与summary相等。独立漂移复算基于原240 Hz物理行，未复用
evaluator几何或累计函数。v1.2 schema审计全部6,882条控制记录和49条事件通过，
证据gap为0。

历史闭合审计实际读完H5唯一dataset、检查动作／后继邻接与最终资格，并完整
解码侧视、腕视和双视角三段原视频：均3,442帧、30 fps。旧格式没有后来加入的
transactional marker和purpose字段，按原完成H5、资格及原生进程退出凭据核查，
缺失的新字段没有被补写。审计后再次核对246个历史源文件SHA，全部保持原值。

完整Progress与HTML在新输出
`outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103/historical_analysis_01`。
HTML引用全部原侧／腕视频及真实帧时间；原始三段视频没有裁剪、覆盖或拼接。
复现入口为现有 `python -m demos.lab_cuvette_progress_v1 episode`、
`replay`、`report`，以及本版本的 `tools/audit_historical_episode.py`、
`tools/summarize_historical.py`。所有输出参数都应使用新路径。

这些结论限于历史合成资产与记录状态。cooked碰撞表面和真实标定仍未知；相对
漂移及控制端点误差不是平台或真机精度认证。历史结果不会进入新的正式评测分母。
