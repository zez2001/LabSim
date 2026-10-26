# GPT debug 04：闭合物理与数据审计

本次原始结论为 `task_success=false / GRASP_SLIP / POLICY_FINISH_REQUEST`；`record_valid`、`record_integrity_valid`、`physics_trustworthy` 均为 true，`success_bc_eligible=false`。器皿已离架并有持物搬运事件，但没有独立确认的装载、释放或撤离，`post_retreat_window.status=unavailable, stable=null`。以下仅是已关闭记录的 CPU 分析，没有新增策略执行、GPU 或 API 调用，也没有更改原标签或评分门槛。

运行代码为 `63410bf9258ba2f9bd0af4d517194523fca6617c`。原进程 PID 826605 已消失，规范退出证明记录 exit 0；实际 51 次 API 决策，其中 50 次执行回执和最后一次主动 finish。6882 个控制转换、27528 个实际执行物理步，终点仿真时间 114.716667 s。TCP 终点到达不能证明器皿到达或全程跟踪精度。

## 接触与滑移的先后

- 71.583333 s 首个 native cup–instrument `CONTACT_FOUND` 的冲量为零，分离约 98 µm；它是接触偏移范围内的几何邻近事件，不能作为已承重的接触。
- 71.675000 s 首个正冲量事件发生于 `/World/Cuvette/Collision/bottomn11` 与 `/World/Instrument/Collision/SourceMesh3`，非零冲量点约为 `[0.207288757, -0.154615745, 0.914000273] m`。点位比选定座底高 27.000273 mm，位于座口/上方特征，原分类为 `entrance_or_top_feature`。当时实际 XY 误差 981.332 µm、倾角 0.053342°、深度 −0.748 µm、座底间距 27.000748 mm、分类座底支撑力 0 N。
- 原双侧抓持参考时刻为 14.112500 s。相对手沿器皿参考 +Z 上移首次达到 50/100/200 µm 分别为 71.754167/71.795833/71.891667 s；首次达到 1 mm 为 72.700000 s。50/100 µm 只是诊断标记，不是新增判分门槛。
- 原 200 µm 杯体相对位置门槛首次越界在 71.891667 s：总漂移 201.491 µm，轴向上移 201.402 µm，配置抓持锚点轴向上移 201.371 µm。初期主要是器皿相对手轴向运动，不能套用旧 teacher 杯底杆臂摇摆的解释。此时仍有双侧接触（1.79676/1.41117 N），分类座底支撑力仍为 0 N。

接触座口之前，合格双侧窗口的杯体漂移最大仅 18.256 µm。接触后继续下发下降目标，器皿逐渐不再随手下降。D34（从零编号）名义 TCP 下降 3 mm、实际 TCP 下降 3.000021 mm，杯底只下降 2.005179 mm；其后 D35–D43 每步 TCP 继续约 3 mm，而杯底每步仅下降约 0.126–0.766 mm，累积相对滑移增长。原独立评分的合格窗口最大位置漂移为 29.690423 mm；D47 失去一侧接触后的瞬态约 29.759272 mm 单列，未冒充原评分值。

全记录没有分类座底支撑力达到 0.1 N 的样本。最大实际深度 10.636616 mm 出现在 111.200000 s，但距选定座底仍有 16.363384 mm，XY 误差 2.238878 mm、倾角 16.047209°、inside=false，不能解释为到底或完成插入。原检查下物理可信为 true；输入表面穿越/有效 cooked geometry 的全局真实精度仍未独立核查。

D47 请求再下降 2 mm 后出现单侧失触，D48 回退 2 mm；D49 保持逻辑开口 9 mm，仅把驱动上限从每指 4 N 降至 0.5 N，杯底仅改变约 −9.044 µm。约 29 mm 的主要滑移早在 71.9 s 开始，不能归因于最后降力。末次 finish 未开爪，也未产生释放或撤离事件。

## 可复核材料

[原数值摘要](summary.json)、[早期轴向标记](early_axial_markers.json)、[50 次执行与器皿跟随 CSV](action_object_following.csv)、[接触至终点的物理时序 CSV](contact_to_finish_physics.csv) 保留实际时间和字段。CSV 去除了每行重复的全部接触点数组，选定原始点保存在摘要，完整点仍在原始无损归档中。

[闭合 H5/归档审计](../gpt_debug_04_closed_read_archive.json) 完整读取 40 个唯一数据集对象，核对时间、标签和 50 个接受回执链；[正常 reader 证明](../../validation/gpt_debug_04_normal_reader.json) 的 ACT/DP `failure` 读取均通过，`success` 按原资格拒绝。H5 没有 external link、外部 dataset storage 或外部 VDS 数据依赖。246 个原非 raw 文件的 SHA256 均保持不变；两份 raw JSONL 从 1,702,402,811 B 无损压至 263,612,326 B，逐份解压 SHA256 与字节数均相等，原 H5、标签、视频、退出证明和模型输入未改。

[实际公开输入交叉审计](wire_inputs_cross_audit.json) 对照 [公开输入证据](../gpt_debug_04_perception/README.md)：51 个公开观测 JSON、102 张实际实发 JPEG、静态 prompt/schema、公开工具调用和回执均保留。它们不是完整 HTTP body，也不包含全部历史 memory/response items 或私有 reasoning。211 个所选原文件 SHA256 与本审计保护清单一致；provider 返回的模型名称只按服务记录报告。

[完整双视角录像](../../media/gpt_debug_04_rim_obstruction_full.mp4) 是原 `dual_view.mp4` 的字节复制，没有重编码、拼接或裁时；3442 帧、1280×480、30 fps、114.733333 s 视频流。CPU 全解码、全部 PTS/源时钟对应和四张关键原帧检查均通过，见[独立媒体回执](../../media/gpt_debug_04_rim_obstruction_full_media_receipt.json)。本证据将该片列为失败尝试，不代表完整任务成功。

公开侧视和腕视中可见杯口相对指垫向掌部移动；本文件使用的碰撞 prim、真值位姿与支撑分类只作离线审计，未输入策略。建议后续在已公开图像基础上验证跨步相对运动记忆与接触后停止逻辑；此处没有声称该改进已经实现或有效。
