# P6 和观察QA最终独立核查

可提交：未发现阻塞。独立重跑三文件52项CPU通过；原完整contracts XML逐case复算630 passed/11 skipped/0 failed，结果SHA匹配、源码运行前后无改。11份helper/profile/base/teacher/physics/scorer保护文件逐字节等于审计基准a80726e。

默认P4原prompt和工具行为保留；P6仅显式temporal。100µm/.1秒请求的world/TCP路由和6控制tick由真实通用工具+CPU回执假件测试，不能叫100µm物理精度。3mm/3秒仍是合法工具输入，P6是模型提示策略，没有隐藏阶段或自动接触guard。

QA默认离线，不创建provider或ledger；显式allow-network才沿用原CubenceClient与共享账本，request allow_retry=False最多一次、120秒deadline。neutral instructions无动作要求，payload不含工具，也没有env/execute/finish。空回答或意外工具响应保留失败，不可能执行机器人。

closed D0–35真实预览145份源SHA前后相同并由本审查再次复核；D7首次公开双侧指力参考/D34 previous/D35 current，4张exact JPEG；CURRENT保持最后。离线seed明确api_sent=false、不造模型回答。实际回答仅保存公开可见文本和安全metadata，不保存私有reasoning、请求头或凭据。

审查未调用API/GPU、未读H5/raw/active，未改runtime或clean checkout。QA真实发送和P6任务表现仍待实际验证；不能把offline preview或CPU fake opener写成模型成绩。
