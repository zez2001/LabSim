# 腕相机实际 API 比较：512low / 640high

root已实际发送两次Responses请求，均返回`gpt-6-astra`。它们来自**同一个INSERT快照（74.866667s）**，每次包含同一原生时刻的side/wrist两张RGB及公开状态；没有GT裁剪、动作工具或机器人控制。

512low（512×384、JPEG q60）耗时8.967505s，input/output为2622/235 tokens；640high（640×480、q60）为8.320215s、2876/244 tokens。每个条件只尝试1次、无重试。共享预算从95次/$5.794462变为97次/$5.873392，本次按配置公开单价的已知usage估算增量为$0.078930；不是账户实际账单，累计账本还包含历史未知usage的保守预留。

两者都识别出浅色器皿、夹指、开盖仪器和座口边界，也都明确不能确认杯底接触、承托或座的可见身份；该INSERT帧没有证明释放、撤离或最终稳定。640high没有新增可确认的任务事实，因此按root决定继续512low并冻结当前图像配置。本次没有修改provider、prompt、runtime或配置。

**不能由两条响应比较普遍延迟或视觉成功率。** 这里只测试一个时刻、每条件一条响应，而且同时改变边长与detail，不能做单因素归因。此处是静态图像能力检查，不是GPT闭环完成任务的证据。

撤离后的视野限制不因此消失：实际teacher末帧中目标器皿部分越出腕视左缘，侧视目标较小且仍有遮挡。完整阶段QA见相邻`teacher_camera_v2_02_stage_visibility`。

`comparison.json`为原始实际结果，含可见回答、usage、requestID和预算；两套`observations/decision_000000/`保留实际JPEG、公有JSON和manifest。全部SHA已核对，JPEG与teacher源快照逐字节相同，没有重新编码。`summary.json`、`comparison.csv`及`budget_usage_excerpt.json`提供紧凑审核结果；`manifest.json`记录来源与本目录哈希。

本整理只读取文件，没有发起新API/GPU调用，没有读取H5、修改原输出或重置预算。source_snapshot中的绝对路径仅为原始来源，阅读本包不依赖该路径。
