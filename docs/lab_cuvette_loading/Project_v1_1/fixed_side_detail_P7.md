# P7 固定公共侧视细节候选

新增 `policy/backends/cubence_project_v1_1_side_detail.py` 及独立 profile `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail.json`。新 profile 的 `max_context_messages=2`，仅保留最近一个完整工具回合。它继承原 P6 的公开 temporal 客户端，在 CURRENT 原消息之前增加一组固定侧视细节，并明确最多附一张历史腕视：优先首次公开双侧接触参考，参考未建立时才上一不同观测；参考本身为 CURRENT 时不重复。P4/P6 的 helper、profile、工具 schema、动作限幅和实际 payload 保持原行为；新增路由会改变控制器实现文件 SHA，应如实记录。

只允许标准 side v3 相机：640×480、固定公开挂点；不同尺寸或挂点在发送前拒绝。固定 ROI `[240,32,520,312]` 输出 480×480，原两相机仍为 640×480/high。它不是检测框、跟踪器、新传感器或更高分辨率采集。没有读取物体/座的坐标、真实深度、教师阶段或结果。

P7 提示在 P6 基础上仅说明如何使用这张图，并要求联合检查腕、手掌、手指、持物和末端臂段相对可见竖直障碍/盖板的净空。没有给出安全高度、碰撞世界坐标、专家路径或自动动作。P6 的入口小步停看要求原样保留；它仍是提示策略，不能将 100µm 请求步长称为平台精度。

运行入口为独立 `run_episode(environment, client, output, ...)`，直接复用 shared runner。原 provider 的一次委托、deadline、重试、模型身份检查、共享 ledger 和实际 usage 结算保持。最终 3–4 图在原 token bound / reserve 前合并；不绕过本地 80k 上下文限制。25 个已闭合公开前缀/context2 的离线重放，公开占位最大 63,462；将由原真实预留反推的全部私有项序列化字节保守分配给保留回合后，上界 67,829，余量 12,171。未知内容未被读取或伪造，未来更长回复仍可能触发限额拒绝。证据见 [闭合前缀预算审计](validation/public_fixed_side_detail_p7_20261027/release/closed_context_bounds/summary.json)。

P7 同时改变细节图、历史图选择和工具会话范围，与旧 P6 属于不同调试条件；不能据其结果作细节图的单因素因果比较。

每个请求目录保留：原 temporal 中间清单（明确未单独发送）、派生 JPEG/metadata、最终公共 projection 与 live input_items 哈希。私有 response reasoning 仍只在 live 协议传递，不落盘；存在私有项时不能重建完整 input_items。原 HTTP body、认证头及 Token 均不保存。

离线示例及标准库复核入口见 [D24 预览](camera/fixed_side_detail_P7_D24_preview/README.md)。它是已闭合公开图片的重放，API=0，动作=0，不能称为 P7 模型或任务结果。

生成命令（默认拒绝覆盖）：

```bash
python -m policy.backends.cubence_project_v1_1_side_detail \
  --source outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000/gpt_control \
  --current-decision 24 \
  --output /tmp/p7-d24-new-preview
```

CPU 测试覆盖精确 JPEG、独立投影数值、4 图实际 fake-transport 预留、历史参考优先级与不重复 CURRENT、CURRENT 最后、重复观测/新 episode/reset、文件冲突拒绝、私有项不落盘、毒化 truth 不可见、原 P4/P6 与冻结 58da 实际 fake-transport payload 相同。CPU 通过不替代真实模型与物理运行。
