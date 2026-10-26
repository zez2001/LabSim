# 闭合公开帧时序可观测性诊断

新增入口 `python -m demos.lab_cuvette_project_v1_1.temporal_observation_qa` 已实现；**默认只离线预览，尚未真实调用 API**。源为已关闭 GPT04 保存的公开 JPEG/JSON；不读取 H5、物理 raw、初态 debug、scorer、物体真值或 teacher 数据，不执行任务或机器人，不赋任务成功标签。

[计划、源 SHA 与实际预览](plan.json) 记录当前 D35、前一不同观测 D34、首次公开双侧接触参考 D7。D7 是由同一真实 temporal helper 顺序重放公开前缀、按有限 `finger_contact_N >0.02 N` 选出的决策观测，不是首次物理接触或有效抓取。4 张图片均为全幅 640×480、高 detail、原 exact JPEG，不重编码或裁图。QA 问题仅放在中立 `instructions` 中；输入顺序是历史参考、CURRENT，CURRENT 的五块内容始终最后。

```bash
python -m demos.lab_cuvette_project_v1_1.temporal_observation_qa \
  --source outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_04/episode_0000/gpt_control \
  --current-decision 35 \
  --output outputs/lab_cuvette_loading/Project_v1_1/public_D35_QA_NEW
```

命令默认不会构造 CubenceClient 或访问账本。它检查实际进程关闭证明及 PID 已不存在；预检全部 D0–D35 的公开 JSON/JPEG/manifest SHA 后才创建新输出，并在结束再次核对 SHA。源目录不能作为输出，输出已存在则拒绝覆盖。离线 capture 只返回 `None`，不伪造模型回复；每个种子文件均记录 `api_sent=false`、`offline_seed=true`、`model_response_generated=false`，不记作 API 决策或 policy 轨迹。

只有显式增加 `--allow-network` 才发送一次 observation-only 请求；本次没有执行带该开关的命令。真实入口复用原 `CubenceClient.request(..., endpoint="responses", allow_retry=False)` 和 `outputs/lab_cuvette_loading/Project_v1/cubence_budget.json`，锁定 gpt-6-astra、low reasoning、原 1024 输出 cap、store=false、无 tools，120 秒截止，最多一次网络尝试。不会删除旧预留、重置账本或重试超时请求。凭据由原 client 仅读取进程环境，CLI 不保存或打印。

QA 不继承 P4/P6 中“返回机器人工具调用”的控制指令。它只问杯口/黑垫/座缘相对变化能否看见，以及自由通行、独立承托的证据和不确定性；不提供离线滑移标签、接触时刻或误差答案。返回 function_call 或没有可见回答时，记录安全失败，绝不执行。保存 actual input_items、exact JPEG、可重建 SHA；真实发送后另存 request ID、model、usage、账本变化和可见回答，隐藏推理、请求头与凭据均不保存。

实际离线预览已通过：源 SHA 未变、D7/D34/D35、4 图、`API_sent=false`、`task_executed=false`；本地保守输入上界 49,150 token，低于原 80,000 上限。证据在 `validation/public_temporal_prompt_p6_qa_ready_20261027/closed_public_D35_preview/`。最终完整 CPU contracts 为 **630 passed /11 skipped /0 failed**，其中传输测试只用临时账本和本地 fake opener；不是实际 API 或物理实验。

观察诊断不能计为新 policy 闭环、数据 episode、完整装载成功，也不能证明 P6 动作合规、100 µm 精度或真实底部承托。它只检验这些既有公开图像对相对变化的可观测性。
