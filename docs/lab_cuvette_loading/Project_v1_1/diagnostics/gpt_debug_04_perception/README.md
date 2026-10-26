# GPT debug04 全部公开观测与实际回执

原结果为 **task_success=false / GRASP_SLIP / POLICY_FINISH_REQUEST**，`record_valid / record_integrity_valid / physics_trustworthy=true`、BC false。此为真实关闭的第四条GPT debug，不是formal5。运行63410bf9258ba2f9bd0af4d517194523fca6617c，PID826605gone、exit0；仅读取此关闭证明后才检查episode，未读正在运行的teacher v7。

## 实际输入保存范围

`gpt_control/observations/decision_000000..000050/`原字节保存全部 **51份公开JSON、102张exact JPEG及manifest**。另保存静态controller/prompt/schema、原policy_trace、公开工具调用与原action_receipts、51行模型动作CSV、退出证明与预算截止快照。逐决策核manifest/JSON/JPEG SHA、request_label、episode/observation/action ID；原所选nonraw文件前后SHA不变。

它们是每次实际发送的公开观测与exact JPEG、静态prompt/schema和公开tool/receipt证据，**不是完整HTTP请求体或全部memory response item组**。未保存或重建可能未记录的私有reasoning内容；usage中的reasoning token计数不是私有推理文本。

实际controller canonical SHA `00c22ce18856b428bd4c8ab1bb7a5d76f7575a96f96b2901457b6f867bded388`。全部51条trace记录requested/returned model均gpt-6-astra，不独立证明上游模型实现。每帧公开JSON白名单不含object truth、teacher phase、评分器内部状态或环境目标坐标。

## 新机位与配置确实进入模型输入

全部帧原生及发送尺寸均640×480、JPEG q60、detail high，无GT crop/旋转；像素变换为单位阵，发送K与原生K相同。side位置匹配v3较低广角，wrist仍为hand挂点v2。实际prompt为v4、context4；task_language包含静态27mm装载目标与panda_hand→right_gripper标定[0,0,0.1]m/wxyz[0,0,0,1]，并明确其不是整手包络。此处是实际输入验证，不再仅render-only；此前render-only证据仍保留原身份，未改写。

## 51决策不等于51条物理动作

51次API/51份公开观测，实际是 **50条动作回执+1次finish**。50条动作均accepted、TCP target_reached，0协议拒绝、0partial interval；共 **6882控制tick / 27528执行物理步**，结束于 **114.716667秒**。finish只请求原独立判分，不推进仿真；CSV中它的duration/tick为空，不补零冒充物理动作。 已执行控制边界的最大TCP跟踪误差为2.975283mm；终点达到请求容差不代表整段动态跟踪具有同样误差，更不代表器皿实际随手下降。

模型先下降220mm、9mm/每指4N闭爪，随后大幅抬升并绕到仪器上方。公开图像可见离架和进入样品腔视野；这不覆盖独立grasp_success=false、transport_success=false。靠近座口后连续3mm/3秒下降；工具达到TCP目标并不能说明器皿随手插入、到达27mm深度或获得承托。

后期图像显示杯与指端相对关系变化。最后2mm回退后，模型保持9mm总开口，将effort cap从4N降到0.5N；随后finish理由明确表示：可见露出长度不能确认名义深度或底部支撑，继续下降/开爪存在风险，因此不释放。它没有实际执行张爪或合格撤离，`post_retreat_window=unavailable`、`stable_after_retreat=null`保留。

不能把最后谨慎finish写成此前没有滑移、完整装载成功或已形成承托；也不能从公开RGB推定精确偏差、碰撞pair、深度或物理根因。确切接触与滑移时刻由另一份关闭物理审计核对。本审计不读取H5、physics/native raw或任何活跃teacher输出。

## 费用与时间

51个trace request ID逐一绑定同一共享ledger的51条已知usage记录，本集本地估算 **4.174990美元**。闭合前209条总估算占用 **16.006522美元**，其中已知usage **15.303832**、7条未知usage保守预留 **0.702690**；不是实付账单，未重置账本，后续新调用不计入此固定截止点。

provider循环1319.609秒、run manifest墙钟与进程总墙钟分别保留；进程总1393.786秒，仿真114.716667秒。每条实际时长与60Hz tick、4个物理步/控制周期一致，相邻回执连续，finish不增时。这支持记录步进一致性，不能称像素和机器人状态严格同刻。

`source_transport_actual_inputs.jpg`和`seat_finish_actual_inputs.jpg`是完整帧阅读拼图，不是新的模型输入；原exactJPEG位于各决策目录。未API/GPU、未改runtime/原标签/原nonraw/旧报告；多个配置同时改变，不能由此单次debug推出因果成功率。
