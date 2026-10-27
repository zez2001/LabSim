# GPT08：主动结束后的三项剩余阻塞

原条件 `9a88ea0b…` 已真实 closed / exit0，34 次请求、仿真终点 65.116667 秒。原结果为 **TASK_INCOMPLETE / POLICY_FINISH_REQUEST**，抓取、清槽、搬运 true，装载、释放、撤离 false；post-retreat unavailable / stable null。不是预算耗尽、碰撞停机或控制器报错。

1. **策略在入口证据不足时主动结束。** D30–32 实际执行了三次世界系 −100µm /0.2s。各 12 control tick /48 physics step，全部正常结束、target_reached true、无 safety stop。实际 TCP 的 Z 位移分别为 −114.323、−100.732、−99.897µm；目标位置误差分别 15.014、0.748、0.126µm。这里是公开机器人回执，不是器皿位移或真实精度。完整 XYZ、起终点、目标、姿态和跟踪摘要见 [CSV](D30_D32_comparison.csv) / [原公开动作回执](D30_D32_public_actions_and_receipts.json)。路径最大位置误差为 68.263、5.178、0.783µm，采样限于已完成 control 边界，不能称物理子步全程上界。

2. **现有公开量不能直接确认座内通行或承托。** 最后两指法向标量约 1.61N，仍表示器皿与夹指的接触，不是座底支撑、插入深度或侧向接触。P9 提供的是机器人自身 frame/INPUT 盒，也不是目标几何传感器。[最后腕图](public_frames/decision_000033/wrist_camera.jpg) 可看见杯底和座口，但透视叠合不证明实际通行。[原 finish](final_public_trace_record.json) 明确称不能从当前双图建立通行、深度和支撑，故保持夹持、不释放。不能把这个理由改写成已检测到 BLOCKED，也不能由 TCP 达标推断已插入。

3. **原 episode 已不可继续，剩余额也不足支持同规模重做。** [源码接口审计](continuation_interface_audit.json) 记录实际提交的函数/行及 SHA：finish 立即评分、结束采集和视频并标记 ended；execute 拒绝结束后的动作；launcher 关闭环境、app 和进程，没有 resume/checkpoint 入口。重置、状态恢复或前缀重放都不是继续这个已闭合 episode，本轮均未执行。

最后共享预算固定前缀为 333 次、占用 **$27.894200**，相对原 $30 仍余 **$2.105800**，并未耗尽。GPT08 已观察的 34 次成本为 $3.050670；余额不足以按这个规模重做类似全程。未来成本会变化，这不是证明所有可能策略都必然超限。原账本与未知 usage 预留保留，没有为消耗余额启动重复 reset、追加 API 或接管动作。

结论：该条件由 policy 主动 finish，GPT 未完成装载、释放与撤离。保留原失败和剩余预算。此薄证据只读公开状态/回执、静态源码与退出证明；没有读取 H5、物理 raw、当前 teacher，未修改源码、标签或原输出。
