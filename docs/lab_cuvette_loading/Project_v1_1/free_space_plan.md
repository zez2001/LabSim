# 固定全位姿的分集自由空间探针

`demos.lab_cuvette_project_v1_1.free_space_plan` 只生成纯 CPU 计划，不接入运行器、不执行仿真或模型调用，不修改场景、guard 或判分。原有 XYZ 回锚的历史记录保持原样，不能用新计划重新标记旧结果。

`build_free_space_plan(pose0, pose1)` 要求两个明确的机器人世界系位姿，格式为 `position_m` 和 `quaternion_wxyz`。可从一次 reset 的机器人观测保存 pose0，再一次性制定 pose1（例如原计划的世界系抬高 30 mm、绕世界 Z 转 0.1 rad）。保存两者后不再从跨动作漂移的姿态重建 anchor。

计划分成三个独立 reset 的 episode：`pose0_world`、`pose1_world`、`pose1_tcp`。每集包含 24 个有稳定 ID 的平移探针：1、5、20、40 mm × XYZ × 正负方向。每个探针前都必须回到固定的完整 xyz+wxyz，而后从一次实际观测的固定起点执行 delta。计划同时保存理想 anchor 下的期望终点；真实起点偏差必须记录，不能假定为零。

建议的运行器适配逻辑如下，action ID / observation ID 继续由既有 `ManualProbe.call` 更新：

```python
plan = build_free_space_plan(saved_pose0, saved_pose1)
for episode in plan["episodes"]:
    facade.reset(0, diagnostic_options)  # 三集各自重新开始计时
    anchor = episode["anchor_pose"]
    for signed_probe in episode["probes"]:
        current = manual_probe.tools.observe()["TCPpose"]
        return_ok = True
        for action in anchor_return_commands(current, anchor):
            if not manual_probe.call(action["tool"], **action["arguments"]):
                # 记录回锚失败并停止/标记该探针不可用；不能只检查 XYZ。
                return_ok = False
                break
        if not return_ok:
            break
        actual_start = manual_probe.tools.observe()["TCPpose"]
        check = anchor_pose_error(actual_start, anchor)
        # 保存 check、actual_start、固定 anchor 与 signed_probe ID。
        if not check["reached"]:
            # 未到达固定全位姿时，不把随后动作算成合格重复探针。
            break
        action = signed_probe["action"]
        if not manual_probe.call(action["tool"], **action["arguments"]):
            break
    # 依次执行 episode["epilogue"]，return_anchor 项仍用上方回锚方法。
    # finalize/关闭当前记录后，再 reset 下一组；保留所有失败。
```

上方是接口示意。接入方应把退出循环的具体原因保存为本探针/本集失败状态，失败后停止 epilogue 或明确记录为恢复诊断；不能在回锚动作失败后继续下发平移。准确的已执行动作与最终结果仍由运行器保存，不能将计划条目当作已执行证据。

`anchor_return_commands(current_pose, anchor)` 从一次当前观测生成绝对路径，每段不超过 25 mm / 0.1 rad，末端严格包含固定 anchor 的 xyz+wxyz。这样 40 mm 探针加上残余跟踪误差后的回程也不需要发送超过公开 40 mm 限幅的单条动作。规划默认 15 mm/s、0.1 rad/s，并按 60 Hz 向上取整动作时长，单条最长不超过 3 秒。

`anchor_pose_error` 同时检查位置和姿态；默认诊断回锚门槛为 0.75 mm / 2 mrad。这是重复探针的起点资格，不改变任务成功门槛；实际误差仍完整报告，尤其不能将 0.75 mm 起点门槛解释成 1 mm 位移的测量精度。

每集末尾回锚后执行 wait 1 秒、闭合至 60 mm、张开至 80 mm、再回锚、绝对固定 anchor 保持 3 秒。三组各自的名义仿真时长约一分钟，计划提供 `estimated_nominal_simulation_seconds`；不含 reset 静置及重试，真实截止时间仍由运行器检查，不能合并三组累计至原 170 秒超时。所有已有碰撞、速度、穿透和记录检查继续生效。

实际 runner 已在 `checked_probes.py::run_checked_free_space` 接入，原计划模块仍为纯 CPU。运行器入口为 `--backend diagnostic --probe free-space-checked`；实际物理验收以独立输出为准。
