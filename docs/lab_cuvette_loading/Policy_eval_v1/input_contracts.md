# Policy_eval_v1：GPT direct 实际输入与执行契约

本文记录本轮冻结 GPT 方案的方法；机器可读身份见 [gpt_identity.json](gpt_identity.json)。π0.5 的 checkpoint、输入处理及动作 chunk 契约由本目录独立 π0.5 身份文档补充，不能按 GPT 配置推断。历史 GPT08 仅作为方法预检参考，不进入本轮正式结果分母。

## 选择的 GPT 方案

使用当前已实际运行过的 P9：`Project_v1_1.public_tools.v9_robot_self_state`。运行 `Project_release_v1` 时显式传 `--provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view_self_state.json`。发布版 launcher 不传该参数仍选旧 P4（512/low、context12）；本轮使用 P9（640/high、context2），不随正式结果更换 profile。

请求模型字符串为 `gpt-6-astra`，通过 Cubence HTTPS `/v1/responses` 调用；服务响应必须返回完全相同的 `model`，否则拒绝执行工具。该核验确认服务声明的模型身份；中转服务背后的权重身份无法独立核实。设置 `reasoning.effort=low`、输出上限 1024 tokens、`store=false`、`parallel_tool_calls=false`；temperature 和策略 seed 未发送，供应商默认值及确定性未知。

profile、prompt、实际 instructions（含 Action limits）、tool schema 及依赖源码 SHA256 见身份 JSON。当前值与 GPT08 留存的 controller 对照一致。`controller.json` 保存每次实际采用的 prompt、工具 schema、profile 及实现哈希；`policy_trace.jsonl` 保存请求和返回模型标识、调用身份、usage、请求动作和实际执行回执。

## 环境原生观察与模型编码

侧相机和腕相机原生帧为同步的 HWC RGB `uint8`，640×480。GPT P9 经 Pillow LANCZOS 最大边 640 处理后，以 JPEG quality60、high detail 发送；当前 640×480 原生帧无尺寸缩放。公开校准包含实际相机安装、姿态、内参及帧时间；逐帧记录原 RGB 和实际发送 JPEG 哈希、缩放矩阵及相应内参。

P9 还发送固定侧图 detail：从本次已编码侧图 JPEG 的像素边界 `[240,32,520,312]` 裁取 280×280 区域，放大至 480×480，并明确标注来源和变换。该固定裁剪没有物体检测器、目标跟踪、新传感器或新的物理分辨率。当前双图始终保留；历史腕图最多一张，优先使用首次公开双侧指接触参考，否则上一不同观察腕图。首次双侧接触参考按公开双指读数各大于 0.02N 选择，不等于有效抓取、承托或阶段成功。

模型可见九维实际关节位置和速度、世界系 actual TCP 位置及 wxyz 四元数、双指总开度（m）、夹爪作用力上限（N）和公开双指接触力。前七个臂关节位置为 rad、速度为 rad/s，后两个指关节为 m、m/s；TCP平移为 m，世界坐标Z向上。这些值未经模型状态标准化。夹爪上限是控制限值，不能当作实测接触力。

P9 的附加机器人自身状态由当前公开 q7、actual TCP 和锁定名义机器人模型计算 link6/link7/hand 的 FK 与 authored INPUT 局部盒。计算不读取场景、物体、目标座或障碍信息；手掌盒不含手指与持物，也不是 cooked 碰撞或通行证明。

H5 及 ACT/DP reader 的 256×256 图像处理是独立数据路径，不是本 GPT 模型的输入处理。π0.5 的模型预处理也应按其实际部署 processor 单独记录。

## 任务文本及评测侧隔离

公开任务指令包含指定来源槽 A1、F6 蓝色干扰器皿、目标内部 A 座 `candidate_far_hinge`、完整装载流程。静态名义目标含器皿 10×10×67.5mm、装载深度 27mm、终态露出长度 40.5mm，以及 TCP/hand 的固定机器人标定。它们是冻结任务描述，不能当作动态器皿位姿、实际插入深度或承托证据。

动态器皿真值位姿、精确孔口对准误差、Teacher waypoint、Progress 阶段和有效插入量、独立 scorer/reward 留在评测侧。公开观察和嵌套相机/TCP数据采用白名单；公开工具回执只包含机器人运动、IK、执行结果与安全信息。`finish` 请求评分后直接结束，不把最终任务评分发送到下一次模型调用。

历史 GPT08 的34份 `public_observation.json` 已递归核查，禁用评测字段精确键命中为0；该核查不是对所有文本语义或供应商内部处理的完整证明。P9 增强输入另有 robot-only 源码路径及逐请求 manifest 支持。正式运行需再次核对首末真实输入摘要。

当前状态与原生 JPEG 位于 `gpt_control/observations/decision_XXXXXX/`；最终增强输入位于 `gpt_control/temporal_visual_context/decision_XXXXXX/input_items_manifest.json`，包含公开投影、图像文件及哈希、完整 wire 输入 canonical 哈希和来源说明。未公开的供应商 reasoning item 只作受控内存上下文处理，不写为报告内容。

## 原生动作与时间口径

GPT 一次调用一个通用工具：`observe`、`move_ee`、`gripper`、`wait` 或 `finish`。没有抓取、搬运、对准或插入宏。

`move_ee` 使用世界系绝对 xyz+wxyz 或世界/TCP系平移+旋转向量增量；平移 m、旋转 rad。每动作平移向量模长上限 0.04m、旋转0.15rad、线速度0.02m/s、角速度0.15rad/s。`gripper` 是双指总开度0–0.08m及每指作用力上限0–8N；慢松爪和卸载由模型显式请求，不调用 Teacher 阶段控制器。move/wait保留上一夹爪请求。

动作时长0.05–3s，量化到60Hz控制周期；每控制周期4个240Hz物理步。每动作先做连续IK预检，回执区分 accepted、execution_finished、target_reached、safety_stopped 和 partial_execution；预检拒绝不推进仿真。原环境的安全阈值、接触锁存、实际跟踪及独立判分保持原配置。

模型推理及网络等待期间物理暂停。公共任务上限使用 `env.timeout_s=170s`，即最多约10200个控制周期；初始化/落稳范围另记录。不要用调用次数代替该共同任务预算。Teacher内部 `control.timeout_s=168` 不作为两策略统一时限。

每集最多160个正常逻辑模型调用，策略墙钟1800s；单次网络超时120s，最多2次重试、退避1s和2s。网络重试共享原账本，保守预留在发网前执行。策略请求或返回不合法、持续预检拒绝、安全终止、预算结束与任务未完成分别保留原原因；不因失败调整参数。

## episode 状态与上下文清空

每次 `run_episode` 创建新工具、空 history、独立P9视觉wrapper；P9还在 episode_id 变化时清空上一腕图与双侧接触参考。当前每次请求保留最近一个完整 response/tool-receipt 回合；更早工具历史丢弃，不跨episode记忆。reset清空环境回执、Progress、记录器及环境episode状态。

## 授权预算与费用解释

评测开始前原共享账本已有333次网络尝试，累计估算USD27.8942；硬上限USD30/1500次，剩余USD2.1058及1167次。没有待决RESERVED。严禁创建空账本、删除旧尝试或提高上限。

每次发网前按保守输入界及最大输出预留：每张图8192 tokens、序列化文本UTF8字节及额外1024输入补量；不是实际tokenizer计数。响应返回usage后按配置费率对账，未知usage继续占用预留。历史P9首请求预留USD0.56558，后续常约USD0.73–0.76；历史GPT08的34次请求实际usage估算USD3.05067，仅用于预算参考。

余额不足保证10个完整GPT任务，甚至不足保证一个历史长度P9任务。正常每集160调用、1800s墙钟及170s仿真上限保留；预检后优先启动一对相同trial，GPT可因原账本保守预留不足而结束，其余计划集明确记为未启动。不能把预算切成大量极短集来凑数量，也不能把未启动计入已启动分母。实际评测推进数量以协议及账本为准。

返回usage可以核对token和本地费用估算；账户倍率、供应商真实账单无法核实，因此 `billing_actual_usd=null`。报告中不将估算冒充实际扣款。凭据仅由原进程环境读取，身份文档、核验脚本和报告均不读取或输出凭据值。

## 离线核验

从项目根目录运行，默认只读并核对最初账本全文件：

```bash
python docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_policy_identity.py
python docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_policy_identity.py --self-test
```

实际运行后允许账本追加，但旧333条前缀、费用上限和策略源码仍须一致：

```bash
python docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_policy_identity.py \
  --allow-budget-progress \
  --output outputs/lab_cuvette_loading/Policy_eval_v1/identity_after_NEW.json
```

输出只含源码/配置哈希、脱敏预算计数和估算，不复制完整ledger；拒绝覆盖输出。脚本不导入模型、读取环境凭据、调用网络或启动GPU。
