# 持物主动视角局部运动：闭合物理核查

真实闭合后读取：21/21 条动作回执；原 GPT06 的16条物理动作只重绑三个ID，另接明确预声明的5条工程诊断动作。实际仿真终点 47.016666667 s，控制转换 2820；后缀实际用时 11.0 s，5条后缀中完成且未部分/安全中止 5 条。结果以 JSON 与逐条 CSV 为准，未执行项保持空值。

本轮 model/provider 调用为0，condition_group=control_diagnostic。原 task_success=False / failure_type=POLICY_BUDGET；实际松爪=False、撤离=False。它仅核查实际持物位姿附近的可逆观察运动，不代表完整装载任务或GPT成功，也不证明通往目标腔体的整条路线安全。人工动作未输入GPT。

`all_declared_and_actual_actions.csv`包括所有21条计划及实际回执，分开记录目标达到、区间结束、部分执行与安全停止；端点误差为实际TCP回执量。`suffix_held_pose_contact_summary.csv`及`suffix_physics_samples.csv`分别给出每条后缀与逐物理步的杯底原点漂移、53mm（以实际配置为准）材料锚点漂移、相对姿态、左右指力、环境接触及来源间隙。后缀局部参考和原scorer持续抓持参考分别保存，未修改原阈值或标签。锚点不是实测接触压力中心；世界旋转不直接当作夹持滑动。

实际禁碰native事件行数 0，第一事件完整保留在`first_forbidden_native_contact.json`；零冲量接触候选不能称为实测承托力。`common_prefix_numeric_comparison.csv`只比较同physics_step/时刻的16动作共同前缀。`summary.json`保存原始独立评分、post_retreat unavailable/null语义、回到后缀起点的TCP误差和限定结论。

独立闭合审计见`../active_view_probe_06_01_closed_read_archive.json`：正常success/failure/all_valid入口均拒绝诊断，失败原因按各filter原始结果记录；全H5、时间对齐、无外部数据链接、原非raw SHA保持及两raw日志完整解压SHA均核查。没有启动新仿真/API、改变物理参数、重标成功或训练。
