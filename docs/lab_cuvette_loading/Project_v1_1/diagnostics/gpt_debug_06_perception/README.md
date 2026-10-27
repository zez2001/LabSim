# GPT06：P7 实际公开输入与主动结束

原结果 **TASK_INCOMPLETE / POLICY_FINISH_REQUEST / task_success=false**；record / integrity / physics true、BC false。独立判分抓取与来源槽清出为 true，搬运、装载、释放、撤离为 false；`post_retreat_window=unavailable`、`stable_after_retreat=null`。没有碰撞，不是完整任务成功。退出证明：运行 `9a4713cf8c71bed4d697625ab052b378608780cc`，PID 1517727 已消失、exit0。闭合前没有读取 episode；未读取 H5、物理 raw 或同时运行的 teacher。

## 实际调用与执行

17 次成功模型决策、**18 次网络尝试**。decision3 一次 PROVIDER_TIMEOUT，随后同一观测重试成功；该次未知 usage 按原预留 $0.706280 占用预算。不能把 17 次决策写成 17 次请求。

实际是 16 条物理动作和一次 finish：2,160 控制 tick / 8,640 执行物理步，累计动作 36 秒，仿真终点 t=36.016667 秒。provider 循环 679.585 秒，原生进程总墙钟 739.509 秒。模型先接近并闭爪，然后九次竖直抬升；它没有请求横向搬运、插入、打开夹爪或撤离。finish 不推进物理时间，也不能当成一次物理动作。

模型最后说明，器皿仍被夹持，但当前图像不足以有把握判断整手/末端臂段穿过直立盖板旁的净空以及到内部座的路线，所以不释放并请求独立评分。它的解释不是不可达证明；实际完整任务仍未完成。

## 保存范围

`gpt_control/` 逐字节复制原生记录的全部公开输入文件、controller/prompt/schema、policy_trace 和 temporal packet。共 17 份公开 JSON、34 张原当前 JPEG、17 张派生 detail JPEG，以及每步实际选中的历史腕图和相应原公开 JSON。17 份准备输入总计 66 个图像块；重试复用同一四图，因此发起的网络尝试共携带 70 个图像块。超时那次是否被上游收到并处理无法确认。

P7 实际配置：side v3 / wrist v2，原双图 640×480 q60/high；固定侧图 ROI `[240,32,520,312]` 派生 480×480 detail；最多一张历史腕视，优先首次公开双侧接触、尚未建立时才上一不同观测，CURRENT 参考不重复；工具会话 context2。D7 建立首次公开双侧接触候选，D8 起使用它作为历史参考。该选择仅依据公开法向读数，不是抓持成功或承托探测器。

核查 CURRENT 五内容块最后、模型动作绑定当前身份、历史来源与时间、原/派生 JPEG SHA、像素中心 A/K、一次原客户端委托与旧账本请求 ID。输入白名单不含物体真值、环境目标坐标、实际插入深度或教师阶段。source / derived 字节和内参均保存；不通过重新编码制造“原图”。

**不是完整 HTTP 请求或完整私有 memory。** 6 份 input_items 没有未保存项，可以完全重建；另 11 份各含一个未保存的私有 provider 项，只能独立验证公开 projection、图像和绑定关系，不能重建完整 input_items。原生 action_receipts 是执行证据，实际模型看到的公开回执以 policy_trace / projection 为准。没有保存 Token、认证头或私有 reasoning 文本。

## 图像可见性与下一步边界

最后的 [完整侧视](gpt_control/observations/decision_000016/side_camera.jpg) 与 [固定 detail](gpt_control/temporal_visual_context/decision_000016/current_side_detail.jpg) 显示手和盖板的轮廓；有透视与深度歧义，detail 还裁去了部分更远臂段。[腕视](gpt_control/observations/decision_000016/wrist_camera.jpg) 主要看见器皿、夹指及架体/桌面，目标腔未被完整看见。不能据这些图像认证整条路径已无碰撞，也不能由 finish 推断没有可行的局部观察动作。

下一候选 P8 只澄清通用主动观察：区分看见的危险与尚未建立的路线；存在有图像依据的局部安全动作时，可以保守可逆地获取不同视角，再观察；原地 observe 不改变机位；没有安全依据或出现实际异常仍停止且不释放。它不提供方向、距离、安全高度或任务路径。P8 的代码/CPU 证据属于另一份候选交付，不能写成这次 GPT06 已执行 P8 或已验证其有效性。

## 固定预算截止

本集估算占用 **$1.428946**，其中已知 usage 成本 $0.722666，未知超时预留 $0.706280。17 份已知回复合计 input 184,186 / output 2,891 tokens。共享账本固定至 253 次尝试：总占用 $20.303572 = 已知 $18.894602 + 8 次未知预留 $1.408970。它不是实付账单，也不是未来实时余额，没有新建账本或删除旧尝试。

208 个原 nonraw 来源 SHA 前后完全一致；原任务标签未修改。`summary.json` 和 `manifest.json` 是首次闭合审计的原证据，后续说明/验证另存，不覆盖它们。仅用 Python 标准库即可脱机复核：

```bash
python3 verify_public_inputs.py
```
