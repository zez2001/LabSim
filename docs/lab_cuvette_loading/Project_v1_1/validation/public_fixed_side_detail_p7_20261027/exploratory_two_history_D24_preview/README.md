# P7 固定侧视细节图：D24 离线候选

本目录是对已闭合 GPT05 第 24 次决策公开图像的**离线准备示例**，没有调用模型，没有执行动作，也没有产生新的任务结果。原 GPT05 是安全碰撞失败；本目录不修改其标签。候选 P7 仍待真实观察及任务验证。

原始侧视为 640×480 JPEG。固定窗口按数组半开边界 `[240,32,520,312]` 裁出 280×280 像素，再用 Pillow LANCZOS 等比放大为 480×480、JPEG quality 60、high detail。窗口固定于 side v3 相机，不由物体坐标、接触信息、检测框或任务阶段选择。原侧视、腕视和两张历史腕视 JPEG 均保持原字节。

可直接查看：

- [原始当前侧视](observations/decision_000024/side_camera.jpg)
- [固定细节图](temporal_visual_context/decision_000024/current_side_detail.jpg)
- [原始当前腕视](observations/decision_000024/wrist_camera.jpg)
- [最终 5 图准备清单](temporal_visual_context/decision_000024/input_items_manifest.json)
- [细节图的来源、像素变换与新内参](temporal_visual_context/decision_000024/current_side_detail.json)
- [离线来源保护与预算检查](preview_summary.json)

细节图中手、末端臂段和打开的盖板比全景更大，但仍有遮挡和透视重叠。放大没有恢复原 JPEG 中不存在的信息，不能确认三维净空，也不能称为碰撞规避效果验证。

五张输入按顺序为：上一不同公开观测的腕视、首次公开双侧接触候选的腕视、当前固定侧视细节、当前完整侧视、当前腕视。原 CURRENT JSON 与两相机的五个内容块仍是最后一条 user 消息，动作使用该条的 episode_id / observation_id。历史触觉参考不等于抓持成功或当前位姿。

像素采用零基像素中心约定：`dst=(src-roi_origin+0.5)*(480/280)-0.5`。新内参为 `K_detail=A*K_source`，相机外参保持原当前侧视值。metadata 给出完整数值；裁剪原点指数组边界，不是相机内参主点。

本离线包只保留 D24 当前原公开 JSON/两张 JPEG、准备中实际选出的两张历史腕视及其原公开 JSON、派生图和清单。它没有复制 D0–D23 的准备目录，没有原会话 response memory、私有 reasoning、完整 HTTP 请求、认证头或 Token。这里的 `full_wire_input_canonical_sha256` 是复用清单字段对**本次离线构造 input_items**的哈希，不能当作原 GPT05 或未来 P7 实际 HTTP 请求哈希。

`pre_detail_input_items_manifest.json` 是未加细节图的中间准备记录，未被单独发送；`input_items_manifest.json` 是本离线候选最终输入，`API_sent=false`。真正运行时，最终 3–5 图会一起交给原客户端执行上下文检查和共享预算预留，只有一次客户端委托，不额外调用 API。

本例不含会话 memory 的原启发式输入预留为 71,709/80,000。原 GPT05 D24 含历史会话的实际预留为 73,707；增加第五图和 P7 文本可能超过原 80,000 上限，届时应在 API 前拒绝。本例不证明完整会话预算可用。全局上限仍为 $30 / 1500 次，8192/图只是本地启发式，不是计费或视觉精度承诺。

仅用 Python 标准库即可脱离工程核验包内字节、5 图重建、CURRENT 顺序和内参：

```bash
python3 verify_offline.py
```

来源：`outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000/gpt_control`，原运行 SHA `58da857e14a0a1152884e13984607a286547a046`。原生进程真实 exit0、PID 1211605 已消失后读取。`preview_summary.json` 中 101 个原路径和 SHA 仅为出处，不要求在脱机机器存在；生成前后全部一致。它们不是本目录承诺包含的文件。
