# 首条真实受控失败与显式11条数据审计

实际合格计数为**10条成功+1条失败，共11条**，距离20/20仍缺成功10、失败19。本步骤只读取两批已闭合的10条natural成功及已闭合首条controlled；新的natural补采进程不在显式文件列表，未打开其活动H5，未扫描episode树。

首条失败UUID为`88633c2e-2b26-497b-834a-5ee0bd369d68`，仿真子进程真实退出0、无中断，日志无损归档完成。父采集CLI因总配额未满退出2不等于仿真异常。

- 器皿已经物理夹持、从架中拔出、搬运、对准并进入INSERT；控制器在实际深度达到1mm后提前停止，没有缩短接口预算。
- `teacher_events.json`在62.383333秒确实产生一次`deterministic_action_deviation`事件。stage=INSERT、value=0.001、unit=m、控制器版本及stop深度与配置和HDF5元数据完全相同。
- 同时刻实际后继状态的深度为**1.016965mm**，比指定停止深度多约16.965μm。事件时间、保存的INSERT阶段、实际深度及同刻停止建议逐项一致；独立判分为`record_valid=true`、`task_success=false`、`failure_type=CONTROLLED_EARLY_STOP`。这是任务未完成的真实轨迹，不能称为孔壁物理受阻。
- 没有松爪或撤离。`post_retreat_window.status=unavailable`，`stable_after_retreat=null`；终止前窗口没有冒充撤离后的稳定窗口。原始失败标签保持false。
- 成功/失败分别通过正常ACT和DP读取，四组action batch均为`[3,16,8]`。成功BC默认只接收10条成功；首条失败按failure过滤单独读取，其训练/验证数量1/0只用于当前单集读取检查，不代表足够的失败训练集。

`collection11_audit.json`含11个明确来源、真实进程退出门控、分组计数及四组读取证据；`actual_INSERT_early_stop_event.json`含全部实际事件对照；`normal_ACT_DP_success_and_failure_read.json`保留原始标签的正常读取结果。检查索引位于`collection_standard/checks/first_failure_index/dataset/episode_data.hdf5`，最终默认dataset索引仍未创建。

后续19条受控数据必须逐条调用本目录`audit_closed_11.py`中的只读`verify_controlled_failure_event(episode)`核查。配置有偏差但未实际触发事件（例如抓取阶段提前失败）的记录，不能仅凭条件组声明填入已执行受控偏差配额；保留其原物理结果，另行分组分析。`config_only_deviation_negative_check.json`实际使用内存事件缺失对照验证了这一门控，没有删除或修改真实事件文件。

本步骤不修改原H5、标签、核心代码、driver、配置、冻结场景或控制器，不启动GPU、训练、DOCX或最终阅读包。自然与受控组的物理质量告警保持原样。
