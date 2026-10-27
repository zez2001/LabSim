# P7 固定侧视细节图：D24 离线候选

本目录是对已闭合 GPT05 第 24 次决策公开图像的**离线准备示例**，没有调用模型，没有执行动作，也没有产生新的任务结果。原 GPT05 是安全碰撞失败；本目录不修改其标签。候选 P7 仍待真实观察及任务验证。

原始侧视为 640×480 JPEG。固定窗口按数组半开边界 `[240,32,520,312]` 裁出 280×280 像素，再用 Pillow LANCZOS 等比放大为 480×480、JPEG quality 60、high detail。窗口固定于 side v3 相机，不由物体坐标、接触信息、检测框或任务阶段选择。原侧视、腕视和被选中的历史腕视 JPEG 均保持原字节。

可直接查看：

- [原始当前侧视](observations/decision_000024/side_camera.jpg)
- [固定细节图](temporal_visual_context/decision_000024/current_side_detail.jpg)
- [原始当前腕视](observations/decision_000024/wrist_camera.jpg)
- [最终 4 图准备清单](temporal_visual_context/decision_000024/input_items_manifest.json)
- [细节图的来源、像素变换与新内参](temporal_visual_context/decision_000024/current_side_detail.json)
- [离线来源保护与预算检查](preview_summary.json)

细节图中手、末端臂段和打开的盖板比全景更大，但仍有遮挡和透视重叠。放大没有恢复原 JPEG 中不存在的信息，不能确认三维净空，也不能称为碰撞规避效果验证。

四张输入按顺序为：首次公开双侧接触候选的腕视、当前固定侧视细节、当前完整侧视、当前腕视。P7 最多附一张历史腕视，优先首次公开双侧接触参考；该参考未建立时才用上一不同观测；参考本身就是 CURRENT 时不重复供图。P6 的原双历史逻辑不变。原 CURRENT JSON 与两相机的五个内容块仍是最后一条 user 消息，动作使用该条的 episode_id / observation_id。历史触觉参考不等于抓持成功或当前位姿。

像素采用零基像素中心约定：`dst=(src-roi_origin+0.5)*(480/280)-0.5`。新内参为 `K_detail=A*K_source`，相机外参保持原当前侧视值。metadata 给出完整数值；裁剪原点指数组边界，不是相机内参主点。

本离线包只保留 D24 当前原公开 JSON/两张 JPEG、实际选中的一张历史腕视及其原公开 JSON、派生图和清单。它没有复制 D0–D23 的准备目录，没有原会话 response memory、私有 reasoning、完整 HTTP 请求、认证头或 Token。这里的 `full_wire_input_canonical_sha256` 是复用清单字段对**本次离线构造 input_items**的哈希，不能当作原 GPT05 或未来 P7 实际 HTTP 请求哈希。

`pre_detail_input_items_manifest.json` 是已按 P7 单历史策略筛选、尚未加细节图的中间准备记录，未被单独发送；`input_items_manifest.json` 是本离线候选最终输入，`API_sent=false`。真正运行时，最终 3–4 图会一起交给原客户端执行上下文检查和共享预算预留，只有一次客户端委托，不额外调用 API。

新 P7 profile 另将工具会话设为 context2（最近一个完整 response/tool-receipt 回合），原 P6 context4 不变。因此 P7 同时改变细节图、历史图筛选和工具会话范围，不能作为视觉单因素优越性比较。对全部 25 个闭合公开前缀的独立重放，最大公开占位预留为 63,462；使用原真实预留约束未保存私有项的总字节，并保守全部分配到保留回合后，上界 67,829/80,000、余量 12,171。这里只量化已闭合样本；未来回复仍可触发原客户端发送前拒绝。全局上限仍为 $30 / 1500 次，8192/图只是本地启发式，不是计费或视觉精度承诺。

仅用 Python 标准库即可脱离工程核验包内字节、4 图重建、CURRENT 顺序和内参：

```bash
python3 verify_offline.py
```

来源：`outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000/gpt_control`，原运行 SHA `58da857e14a0a1152884e13984607a286547a046`。原生进程真实 exit0、PID 1211605 已消失后读取。`preview_summary.json` 中 101 个原路径和 SHA 仅为出处，不要求在脱机机器存在；生成前后全部一致。它们不是本目录承诺包含的文件。
