# GPT07：P8 公开输入与持物主动结束

实际运行提交 `42264193cc7fea92b467e14d29f28e7a05ba421f`，PID 1797219 已消失、真实 exit0。**原结果 TASK_INCOMPLETE / POLICY_FINISH_REQUEST / task_success=false**。record、integrity、physics 均 true，BC false；抓取、来源槽清出、搬运为 true，装载、释放、撤离为 false。`post_retreat_window=unavailable`、`stable_after_retreat=null`。模型保持夹持并主动结束，没有把工具 finish 写成成功。

本审计的持久 watcher 先等待真实退出证明、PID 消失及精确运行提交，再执行一次公开输入审计，exit0。没有读取 active episode、H5、物理 raw 或同时运行的 teacher；没有调用 API/GPU。物理接触与完整 H5 核验属于另一个闭合审计，不由本目录的图像推断代替。

## 实际请求、执行与预算

46 个模型决策、46 次真实网络请求，全部有已知 usage；没有重试或新增未知预留。所有返回模型身份均为 `gpt-6-astra`。45 条物理动作与一次 finish，合计 **5,400 control tick / 21,600 executed physics step / 90 秒动作时间**；仿真从 t=0.016667 到 t=90.016667。provider 循环墙钟 1,173.828 秒，原生进程墙钟 1,245.606 秒。动作、原回执与部分/错误行的实际状态保留在 [逐步动作](actions.csv) 和 [原末行](final_raw_trace_record.json)，没有补零伪造未执行的动作。

本集已知 usage 为 input 433,240 / output 8,091 tokens，按原公开费率估算 **$4.539958**。共享旧账本固定截至 299 次尝试：总占用 **$24.843530 = 已知 usage $23.434560 + 8 次未知预留 $1.408970**；相对原 $30 门槛剩余 $5.156470。这里是固定闭合前缀的本地估算，不是账单或未来实时余额。未新建预算、删除尝试或提高限额。

## 实际公开输入范围

完整复制原 `gpt_control/`：46 份公开状态 JSON、92 张当前原 JPEG、46 张派生 detail JPEG、实际选入的历史腕图和原公开状态，以及静态 controller/prompt/schema、公开 tool call/receipt、policy trace 和 temporal packet。46 份准备输入对应 182 个图像块；本集无重试，因此实际请求也对应 182 个图像块。

实际 P8 使用同 P7 的侧视 v3 / 腕视 v2、640×480 q60/high，固定侧视 ROI `[240,32,520,312]` → 480×480 detail；最多一张历史腕图，优先首次公开双侧接触参考，否则上一不同观测。D7 建立公开双侧接触候选，D8 起使用该参考；它不是抓取成功检测器。context2 只保留一个完整工具回合。CURRENT 的原五内容块仍为最后一组。

审计逐步核查当前身份、历史来源/时间、源与派生 JPEG SHA、像素中心 A/K 变换、实际 prompt/instructions SHA、P8 元数据和旧账本 request ID。没有把物体位姿、目标座世界坐标、实际插入深度、支撑力真值、碰撞结果或 teacher 阶段加入公开输入。P8 只是通用主动观察提示，没有自动动作、方向、安全高度或任务路线。

**本目录不是完整 HTTP body 或完整私有 memory。** 8 份 input_items 的全部内容可重建并匹配原 full-input hash；38 份各有未保存的私有 provider 项，只核验其公开 projection、精确图像、身份及来源，不能重建完整 input_items。没有保存私有 reasoning 文本、Token 或认证头。原生 `action_receipts.jsonl` 是执行证据；模型实际看到哪些公开回执，以原 policy trace / projection 为准。

## 最后一帧的可见性与局限

[D45 原侧视](gpt_control/observations/decision_000045/side_camera.jpg) 显示整机、打开盖板、末端臂段及持物手爪，但单幅透视仍不能直接给出整手与盖板之间的三维净空。[D45 原腕视](gpt_control/observations/decision_000045/wrist_camera.jpg) 能看见被夹器皿和腔内两个座，器皿仍在座上方；[固定 detail](gpt_control/temporal_visual_context/decision_000045/current_side_detail.jpg) 只放大已有像素，不是新机位或新分辨率测量。图像可见目标不等于已建立实际承托。

模型原 finish 理由是：当前图像不能确认继续下降时的整手净空、插入深度或座内支撑，因此保持夹持、不释放并请求独立评分。它没有因真实碰撞被终止，也没有证明不存在可行的下一局部动作。P8 确实比 GPT06 多执行了搬运与接近，但这是不同调试运行，不能由两次样本推出提示的成功率或因果优越性。尚未执行装载与释放，因此不能称 100µm 停看插入策略或支撑交接已在本集中通过。

## 脱机复核

556 个原 nonraw 来源文件在复制前后 SHA 完全一致。首次闭合 `summary.json` / `manifest.json` 保留不覆盖；本说明与验证器另存。仅需 Python 标准库：

```bash
python3 verify_public_inputs.py
```

验证器核对原副本 SHA、46 组公开图像/内参/身份、8 份可重建输入、45 物理回执的实际时间/tick，以及原失败标签；不访问网络或仿真。
