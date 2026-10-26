# GPT debug03 公开观测与安全停止证据

本次真实运行保持原判分 **SAFETY_COLLISION / ROBOT_ENVIRONMENT_COLLISION**，`task_success=false`、`workflow_success=false`；`record_valid`、`record_integrity_valid`、`physics_trustworthy` 均为 true。这是独立 standard reset 的第三次 GPT 调试，不是 formal5，也不表示此前 teacher 已通过。

## 保存范围与复核方法

- `gpt_control/observations/decision_000000..000014/`：15次决策的全部公开观测 JSON、30张实际编码发送的 exact JPEG 及原始 manifest，逐字节复制。
- `gpt_control/controller.json`：当次静态 system prompt、工具 schema、provider 配置及控制器版本；`policy_trace.jsonl` 保存公开工具调用和回执，原文件不改写。
- `action_receipts.jsonl`、`action_sequence.csv`：原回执及15条动作的请求/实际时长、tick、TCP运动、指端接触及开口/力上限。
- `source_lift_actual_inputs.jpg`、`lateral_safety_actual_inputs.jpg`：完整双视图阅读拼图，不裁剪；原 JPEG 才是实际编码图像证据，拼图为另存的阅读辅助。
- `raw_result_label_excerpt.json`：不变的原任务标签、阶段结果与 post-retreat 的 unavailable/null。
- `manifest.json`：全部所选源文件的前后 SHA、包内文件 SHA。`summary.json` 提供每个观测、请求标签、动作和原回执的绑定核查。

这些材料是**每次实际发送的公开观测 JSON 和两张 exact JPEG、静态 prompt/schema、公开工具调用/回执**，不是完整 HTTP 原始请求体。实际 HTTP 还含当前任务及内存中的完整 response item groups；可能未记录的私有 reasoning items 不在本包中。不能声称由这些文件重建了完整 HTTP 上下文或保存了私有推理内容。

## 实际执行与原始结果

关闭证明为 PID398972 已消失、exit0；运行提交 `109e637bcb264458ffc231f4e052e60ff6764242`。当次控制器 canonical SHA 为 `c4ae3ca7c750ae900b799bff3597c5869da74af06ccc55b12a853d8f39e0e361`，prompt v3、context4。公开任务语言仅包含配置中的静态目标：candidate_far_hinge、名义27mm装载深度、67.5mm器皿高度和40.5mm露出高度；不是实时器皿位姿、插入深度或隐藏测量。

共15次API请求、0次协议拒绝，15条动作均被接受。前14条TCP终点达到请求范围；最后一条请求2秒/120tick，实际 **1.65秒/99tick** 后触发安全停止，`partial_execution=true`、`target_reached=false`、`stop_domain=safety`。总计 **1779控制tick / 7116物理步**，仿真终止于 **29.666667秒**。各回执实际时长与60Hz tick一致、相邻仿真时刻连续；这支持请求期间暂停步进的记录一致性，不等同于证明像素与状态完全同刻。

公开动作先下降5×40mm+32mm，随后请求9mm开口、每指4N上限闭爪，再抬升4×40mm。14.0167秒闭爪后的公开左右接触为1.183084/2.011403N；此后图像可见器皿随手离开架体，但不能覆盖独立判分 `grasp_success=false`。原 `source_slot_cleared=true` 保留。

22.0167秒开始连续请求4次 `[36,16,0]mm` 横向移动，没有再增加高度。侧视显示整手逐渐靠近仪器上部；腕视主要保留被持器皿和来源架，对前方整手—仪器净空信息有限。最后一张实际模型输入位于28.0167秒，**早于停止1.65秒**；本包不伪造停止瞬间的新观测，也不从RGB猜测具体碰撞prim。

最后实际TCP合位移约32.800mm（X分量30.081mm），剩余请求终点误差约6.603mm，回执最大控制边界跟踪误差约0.406mm。剩余距离来自安全中止，不能称为执行器无界跳变或213mm异常复发。准确值以 `action_sequence.csv` 和原回执为准。

本次没有执行插入、支撑交接、松爪或独立确认的撤离。`release_observed=false`、`retreat_observed=false`、`post_retreat_window.status=unavailable`、`stable_after_retreat=null` 均保留，不能将上抬或部分横移写为完整装载成功。碰撞 actor 和接触位置由独立关闭物理审计核实，此公开输入审计不读取器皿真值、H5、原始物理或 native-contact 日志。

## 界限与预算

全部图像来自原生640×480完整帧，缩到512×384、JPEG q60、detail low，无 GT crop；所有 JPEG/公开 JSON/manifest/trace SHA 及 episode/observation/action ID 绑定已核对。原输入与所选nonraw源文件前后SHA一致。静态prompt与schema保留，不含凭据。最后error trace没有显式记录returned_model字段，前14条有记录且均为gpt-6-astra；本分析不为缺失字段补值。

GPT03闭合时共享ledger快照为156次请求、估算占用11.743002美元；本集15次、估算增量1.106340美元。该占用包括此前未知usage预留，不是最终实付账单，未重置账本。本次过程墙钟386.557秒、run manifest335.721秒、provider循环331.338秒分开列出，不能混作仿真时长。

与debug01/02相比，prompt、静态公开目标、context长度及模型选取的抓取/抬升动作均有变化。单次运行不能分离某个改动的因果效应，也不能估计稳定成功率。本分析未调用API/GPU，未改运行代码、配置、原始标签、原nonraw输出或报告草稿。
