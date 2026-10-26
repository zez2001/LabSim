# GPT debug01：实际输入与搬运碰撞复核

本次为真实 GPT 闭环尝试的只读复核。原始结果为 **SAFETY_COLLISION / ROBOT_ENVIRONMENT_COLLISION**，`record_valid=true`、`physics_trustworthy=true`、`task_success=false`。过程确实完成了接近、闭爪、抬升及第一段搬运；没有完成腔内插入、支撑交接、释放或撤离。不能将它归为执行器失稳、接口拒绝或完整任务成功。

## 模型实际看到了什么

包内 `gpt_control/observations/decision_000000..000010/` 保留全部11次决策的实际发送 JPEG、公开观测和原始 manifest。均为512×384、JPEG q60、detail low、无裁剪，源录像/调试真值未用作模型输入。全部 JPEG、公开JSON和manifest均重新核对 SHA、episode/observation绑定。`key_actual_inputs_contact_sheet.jpg` 是完整图像的阅读拼图；原 JPEG 未重新编码。

- decision0，0.0167秒：初始整体关系；侧视可见来源架、整手和单台开盖仪器。
- decision6，14.5167秒：即将闭爪；来源槽中的浅色器皿位于两指之间，下段受架壁遮挡。
- decision7，16.5167秒：闭爪后，实际开口约10.699mm，左右公开接触读数约1.201/2.103N；请求为9mm、每指5N上限。这些力是观测，5N是上限，不能混为同一物理量。
- decision9，21.5167秒：两次40mm抬升后，腕视能看见器皿与下方来源架分离；侧视同时能看见仪器近侧高壁与整手/腕部的相对关系。随后请求同高度横向移动`[37,14,0]mm`。
- decision10，24.0167秒：第一段搬运结束，侧视中整手与机身的投影间隙进一步缩小；腕视仍主要覆盖器皿和来源架，前方仪器高壁基本未进入有效观察区。模型再次请求相同方向、同高度的横向段，在执行49tick后安全停止。

这里没有保存模型隐藏推理，不能断言其主观上如何估计距离。“低估净空”是对动作序列的解释：在可见高壁旁，采用两段连续的同高度横移，没有先建立能够覆盖整手包络的净空证据。每段开始均已自动提供新图，不能因为没有额外调用`observe`就说模型未收到图像。

## 观测是否足够

侧视足以揭示存在高壁，并支持更保守的整体净空规划；腕视清楚呈现夹持和器皿保持，但在这两个横移时刻对前向机身边缘的覆盖较弱。两张RGB及标定并不等于障碍物三维网格或整手碰撞包络，也不能仅凭投影缝隙认证毫米级安全距离。公开接口没有深度图、物体真值或自动避障宏。不能由这些图片独立定位究竟哪个机器人link与哪个prim相碰；公开回执只给出`ROBOT_ENVIRONMENT_COLLISION`。

因此可以增加纯通用说明：规划整个手体、手指、腕部及被持物的扫掠空间；在跨越凸起结构前先由双视角建立保守净空；近障碍使用更短的有界动作并重新核对。不要给目标坐标、专家路径或对象真值。连续IK预检只验证运动学，其回执已明确不认证碰撞安全。

## 执行器与安全标签

11次API决策、0次协议拒绝。前10个动作均通过TCP终点检查，最后动作接受后部分执行，`target_reached=false`、`safety_stopped=true`、`partial_execution=true`、`stop_domain=safety`。全程执行1489控制tick、5956物理步；24.8333秒停止，进程真实退出0。

最后请求2.5秒/150tick，实际仅0.816667秒/49tick。最后段最大跟踪误差 **0.259601mm**；未完成目标的剩余距离 **26.880593mm** 是安全停止后的目标余差，不是执行器跳变或跟踪误差。最后实际TCP仅移动约12.68mm。夹持请求9mm/5N在搬运期间持续保持，没有被move工具重置。

`action_sequence.csv` 给出全部动作、请求/实际位移、时长、tick、跟踪误差及安全语义。`raw_result_label_excerpt.json` 原样摘录最终标签并绑定源文件SHA；不修改历史评分。未读取debug物体位姿、physics_records或HDF5，未运行API/GPU，未改代码/配置/原输出。

## 文件入口

- `summary.json`：结构化观察、限制和来源范围。
- `action_sequence.csv`：11个实际动作的小表。
- `gpt_control/policy_trace.jsonl`、`action_receipts.jsonl`：原始模型工具调用和实际回执。
- `gpt_control/controller.json`：当次真实prompt、工具和限幅，不含密钥。
- `gpt_control/observations/`：模型实际收到的完整JPEG与公开状态。
- `process_exit.json`、`raw_result_label_excerpt.json`：关闭证据与原始分类。
- `manifest.json`：包内文件SHA及原始来源。此为独立精简证据，不包含H5、视频、原始接触/物理大日志。
