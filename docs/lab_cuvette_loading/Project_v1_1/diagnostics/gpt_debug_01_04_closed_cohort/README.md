# GPT01至04 已闭合调试汇总

[四行CSV](episodes.csv)与[完整小JSON](summary.json)只统计Project_v1_1四个不同调试条件，不是正式成功率，与旧Project_v1 formal5完全分开，也不含未来GPT05、取消队列、观察QA或teacher。原全任务结果四条都false：三条安全域、一条任务域；四条record/integrity/physics均true，既有正常failure ACT/DP读取证据均通过。

实际runtime依次09b0c41、c793a12、109e637、63410bf。前两次原退出proof不含commit，因此从各自原release_metadata.actual_execution_commit核实，不拿当前HEAD补填。首次prompt未序列化版本，保留null/unversioned及准确prompt SHA；后续是原v2/v3/v4。前三次原高侧视+腕v2，512×384 q60 low；04为lower side v3+腕v2，640×480 q60 high。context为12/12/4/4；无temporal历史输入。

每条最远独立required event都为held_transport_observed，之后的物理进展另记：01手掌碰机身、02到座缘受阻后继续压和开爪、03左指碰机身、04座缘相对滑移后主动finish。不能把模型说“插入”或TCP到位代替独立loaded/support事件。

02确实执行11mm和40mm开爪，公开下一观测测到38.778mm和双指零接触，并执行过35mm回升及下一次部分回升；原独立release_observed/retreat_observed仍false。它不属于正确承托后的释放撤离。四条post_retreat_window都unavailable，stable_after_retreat均null；terminal_window另列，不把中止前窗口当撤离后稳定。

110个实际请求ID逐一join原Project_v1共享ledger，全部有usage，公开价估算合计10.044600美元，不是总账单或包含其他probe/QA/正式组的费用。原输出SHA复核不变。原independent_score完整性快照仍null/collector_pending，最终result在streaming_collector_checks_at_flush_close为true；两者明确区分而不覆盖。只读取JSON、公开trace与已有闭合审计，不打开H5或大raw、不新运行仿真/reader/API/GPU、不修改标签。
