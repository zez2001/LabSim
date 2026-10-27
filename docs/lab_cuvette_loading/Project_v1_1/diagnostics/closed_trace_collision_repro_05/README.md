# GPT05 碰撞的闭合轨迹复现

离线诊断完整重放25条原始通用工具请求，包括末尾error行的world X +35mm/2s。原GPT05与重放均在49.916667s、2994控制步后返回SAFETY_COLLISION；最后一条请求实际执行114/120步。诊断调用API为0，不是新增GPT尝试，更不是完整装载成功。

11981条物理状态按physics_step 0–11980逐条配对，无缺行、插值或补零。实际关节、下发关节目标、TCP位姿、器皿位姿/质心及器皿相对手爪位姿的选定字段，逐个已记录浮点数完全相同。三组指力字段并非逐位相同：finger_contact最大分量差4.768371582e-7N，normal向量3.576278687e-7N，friction向量8.940696716e-8N；差异内部原因未确认。不要将此结果写成所有物理字节或所有接触力完全一致。

首次禁碰callback的完整内容相同：physics_step11978、49.908333333s，panda_link6几何与Instrument/Collision/SourceMesh5。callback原始冲量/力和分离值保留其原约定，不代表真实标定力。控制区间结束比该首次事件晚两个物理步，结束时刻为49.916667s。

文件：

- `run_results.csv`：两轮结果小表及正常reader实际资格。
- `numeric_field_comparison.csv`：各已存在字段的有效/空值行数、最大分量与L2差；未测量几何项保持null，不写成0或无穿透。
- `action_request_and_receipt_comparison.csv`：25条请求除三个ID之外的参数，以及实际执行步数、时长和停止原因均相同。
- `first_forbidden_contacts.json`：两轮首次禁碰原始callback与接触点。
- `summary.json` / `source_manifest.json`：方法、范围、源SHA及生成文件SHA。

闭合H5全读、正常reader和无损归档证据另见 `../collision_replay_05_01_closed_read_archive.json` 与 `../../validation/collision_replay_05_01_normal_reader.json`。重放40个dataset全读、160个原nonraw文件SHA不变；两个raw日志 decoded SHA/bytes与归档前相同。success过滤先因原task_success=false没有成功样本；failure/all_valid到达独立reader的condition_group门并拒绝control_diagnostic。所有原始评分、任务结果及完整性标签保持不变。

该证据说明：同一固定场景、同一机器和软件下，原请求能复现同一机器人-盖板碰撞与失败区间。它不验证跨机器一致性、一般成功率、真实精度，也没有验证安全完整装载路线。
