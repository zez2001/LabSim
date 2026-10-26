# GPT debug02 实际输入与执行证据

原结果保持 **SAFETY_GEOMETRY_VIOLATION / INPUT_MATERIAL_PENETRATION**，`record_valid=true`、`record_integrity_valid=true`、`physics_trustworthy=true`、`task_success=false`、BC不合格。此为已实际运行、真实关闭的第二次GPT调试；不是完整成功、旧debug01的手碰机身、执行器失稳或provider故障。

本包完整覆盖33次决策的公开观测快照：保存当次公开观测JSON、两张实际发送的编码JPEG，以及公开工具调用/回执和静态prompt/schema。它不是完整HTTP原始请求归档。实际每次HTTP请求还含system/tools、当前任务消息和memory中的完整response item组，后者可能包含本包未记录的私有reasoning items；不能据本包完整重建全部请求上下文。字节一致仅指与原保存文件及编码JPEG一致，不指完整HTTP字节流，也不宣称私有推理内容已保存。

## 可直接审阅的文件

- `gpt_control/observations/decision_000000..000032/`：全部33次实际发送的两路JPEG、公开JSON及原始manifest，原字节复制。
- `gpt_control/controller.json`、`policy_trace.jsonl`、`summary.json`：当次真实prompt/工具、模型调用及预算快照，不含API凭据。
- `action_receipts.jsonl`、`action_sequence.csv`：原始执行回执和全部动作的小表；TCP到达与器皿任务结果分开。
- `source_transport_actual_inputs.jpg`、`entry_open_retreat_actual_inputs.jpg`：若干关键时点的完整图像阅读拼图，无裁剪。判断细节应打开原JPEG。
- `raw_result_label_excerpt.json`：保留原最终分类及post-retreat的unavailable/null，附源SHA。
- `manifest.json`：全部所选原文件及包内文件SHA；`summary.json`给出逐决策观测/动作绑定核查。

## 实际发生了哪些公开动作

闭合证明为PID147063已退出、exit0；本次33次API决策、0次协议拒绝，33条动作均接受，前32个TCP终点到达。共3591控制tick、14364执行物理步，终止于59.866667秒。最后动作请求2秒/120tick，实际0.85秒/51tick，`safety_stopped=true`、`partial_execution=true`、`stop_domain=safety`。

从公开动作与图像可见，9mm/每指4N上限闭爪后，先请求8次40mm向上TCP动作，再进行高位横向搬运并逐步下降到可见座口。它比debug01两次抬升后同高度横移推进更远；不能仅凭两个不同prompt的debug就推断通用成功率或单因素因果。

在52.0167秒的decision26腕视中，器皿底已到座口附近；53.0167、54.0167秒仍连续下发8mm下降。工具`target_reached=true`只说明TCP达到请求终点，不能说明器皿随手进入或已经到底承托。此处器皿与手指的可见相对关系发生变化，但RGB不提供可靠完整插入深度或底部支撑力。

55.0167秒decision29的公开左右接触分别为 **0 / 3.875082N**，已出现明显单侧接触。随后模型才请求11mm开口、每指0.5N上限卸载；下一次请求40mm张开。57.0167秒的图像能看见指间间隙，双侧接触为零，但这本身不能证明器皿在正确支撑位稳定。59.0167秒最后一张实际输入已经可见器皿倾斜；之后第二段向上TCP动作部分执行并触发输入材料几何安全门槛。

最后实际发送图像在安全停止前0.85秒；本包没有伪造停止瞬间的新模型观测。原`post_retreat_window.status=unavailable`、`stable_after_retreat=null`保留，不能把执行过向上命令当作独立判分确认的完整退让。

## 净空与接触语义

本次真实prompt增加的是通用整手与持物净空提醒，不包含障碍坐标、安全高度oracle或专家轨迹。全部图像仍为原生640×480完整缩到512×384、JPEG q60、detail low，无GT裁剪；全部JPEG、公开JSON、manifest和trace绑定已核SHA。策略没有器皿真值、teacher阶段或内部评分状态。

下降、卸载和退让时需要结合双视图、实际指端接触及相对运动判断。TCP成功到达、相机中杯底看起来进入边框、或张爪后的短暂竖直外观都不能直接计为成功。确切偏差、阻挡位置、材料穿透或姿态数值属于另一份已关闭物理日志的离线核查；本公开输入审计不读取这些真值，也不把它们用于policy提示。

GPT02闭合时共享ledger快照为141次请求、估算占用10.636662美元；本集33次、估算增量3.699790美元。它包括此前账本占用和未知usage预留，不是最终实付账单，也没有重置ledger。

本任务只复制已关闭的精简公开证据。没有读取H5、physics_records、native_contact或任何活跃teacher输出；未调用API/GPU，未修改原nonraw文件、运行代码、评分或报告draft。完整H5读取/原始接触与几何分析由独立关闭审计另行交叉核实。
