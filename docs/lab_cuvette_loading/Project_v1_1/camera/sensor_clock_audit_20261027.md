# 公开图像时间与机器人状态时间：8.33 ms 差值审计

结论：本次已保存的6个grasp_transport_02快照中，约+8.33ms的图像时间差与已记录的引擎时钟起点完全相符；后续微秒级增长也精确符合引擎physics step_size的浮点表示。这不是“旧了一帧”的证据，当前没有因此阻塞GPT的确定性接口故障。原始sensor/state时间均应保留，不通过覆盖时间戳制造一致。

本分析只读闭合诊断记录、公开预览JSON和安装源码，没有API/GPU/H5读写。预览并未真正发送API，不能据此声称模型收到过这些帧。

## 两个时钟

- 公开`simulation_time`：本episode已执行物理步数/240，单位秒。
- 相机`sensor_rendering_time_s`：Isaac引擎累积physics callback step_size后的秒数。
- reset在build_context之后记录`engine_clock_origin_s=0.008333333767950535`，episode计数随后从0重新累计。初始化第4步对外首次公开：episode=0.0166666666667s，而sensor=0.0250000013039s。
- 已安装SimulationContext源码`simulation_context.py:1420`为`self._current_time += step_size`。其current_time属性返回该累积量。

实际6个快照同时满足：

```text
t_episode = physics_steps / 240
sensor_time = engine_origin + physics_steps * float32(1/240)
float32(1/240) = 0.004166666883975267 seconds
```

例如decision_000004：episode=27.233333333333334s（6536物理步），sensor=27.2416680874303s。减origin后的差值为1.420329µs；使用记录对应的step_size公式后残差精确为0。decision_000005在31.233333333333334s时对应差值1.628945µs，公式残差同样为0。

所有6对side/wrist sensor timestamp相同，初始和最终camera metadata的sensor时间也与读时world current_time相同，`repeated_sensor_frame=false`。rendering_frame字段实际为ReferenceTime分子/分母token，不是control tick或录像帧号。

## 读取顺序和证据限制

环境每个控制步先执行4个240Hz物理步，再更新articulation kinematics、render flush、读取两张原生RGB，最后构造公开观测。公开状态和相机均保留各自原始时间。provider compact metadata保留sensor数值，但省略时钟说明文字；不能因为与episode秒数不相等就判断滞后。

该顺序、时间等式和frame token能排查本次8.33ms误解，**不能独立证明渲染像素与物理状态严格同刻**。本次只核对6个已存快照及初始/最终metadata，没有核对每个控制帧的像素关联。新腕相机仍需真实渲染下的机器人中心投影和运动关联检查。

`observe`本身不推进仿真，所以在同一物理时刻重复读取相同frame完全合法。不要把暂停推理期间相同的图像哈希或时间戳本身当作旧帧故障。

机器可读逐快照数值、源码位置、文件SHA256及限制见`sensor_clock_audit_20261027.json`。本次未修改prompt、core、相机配置、原始时间或输出。
