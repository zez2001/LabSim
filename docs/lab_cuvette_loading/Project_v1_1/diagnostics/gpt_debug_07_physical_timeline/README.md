# gpt_debug_07：闭合后实际物理时间线

真实 runtime `42264193cc7fea92b467e14d29f28e7a05ba421f`，PID1797219已退出，退出码0。实际90.016666667s / 5400控制转换；完整任务 `False` / `TASK_INCOMPLETE`，终止原因 `POLICY_FINISH_REQUEST`。本分析不修改标签或阈值。

以真实物理事件行核对抓持、离架、搬运、承托、脱指与撤离，见`actual_event_timeline.csv`。`post_retreat_recomputed.json`从原始实际窗口逐物理步重算3秒承托/脱指/位姿稳定等，缺测保留null；terminal_window单独保存。`grasp_reference_recomputed.json`保留实际接触持续参考、底部原点与材料锚点漂移、各次抓持和首次越界；旋转杆臂项不叫纯轴向滑移。`first_forbidden_native_contact.json`保留第一真实禁碰pair/时刻/点，不把零冲量候选叫支撑力。

是否完整成功以`summary.json`的实际事件及重算窗口为依据，不以模型说完成或动作名判断。H5读取、正常ACT/DP filter与无损归档另见`../gpt_debug_07_closed_read_archive.json`。离线分析0API/0GPU；物理质量告警与真实校准/有效烹饪几何未知项保留。
