# 提取初期旋转：执行时序补充（2026-10-27）

**preload01 的EXTRACT名义四元数始终固定，不能把失败归因于teacher真值纠姿。** 杯转动远大于手转动；新的冻结XY对照可评估后续反馈影响，但大幅XY反应发生在首次越界之后，现有数据尚未证明它是初始摇摆原因。这里只补充已关闭原轨迹，不改变原评分或已stage证据。

| 从各自EXTRACT/首lift指令开始的0.6 s内 | source_hold01 | preload01 | grasp04 |
|---|---:|---:|---:|
| requested/nominal目标四元数变化 | 0°，唯一1组 | 0°，唯一1组 | 0°，唯一1组 |
| 实际hand最大角变化 | .004085° | .003818° | .017747° |
| 杯世界最大角变化 | .316740° | 1.752762° | .310754° |
| 原scorer双侧持续参考相对起点 | −.770833 s | −.762500 s | **+.070833 s** |

sourcehold/preload配置均明确extract_orientation_feedback=false；父类EXTRACT使用该布尔，TRANSPORT才恢复默认姿态反馈。robot_tracking会小幅调整有效IK/command FK，不能与requested目标或actual hand混为一谈。preload有效IK角变化最大.010429°、command FK .010343°，仍远小于杯体1.75°。角度是各自起点的相对旋转范数，不是硬件精度或全部杯倾斜角。

![真实杯、手与命令角变化](cup_and_hand_rotation.png)

## 首次越界：先执行，后反应

物理日志在控制边界记录的是刚完成区间：(t_before,t_after]。使用该边界观测生成的新动作是后继反应。先前 [原始orientation摘要](../teacher_preload_01_orientation_review/summary.json) 中`control_tick_at_or_nearest_first200`明确为最近tick，边界上可能是后继动作；不能据其20 µm目标认定先因。本补充保留其原SHA，并单独列执行区间和后继区间。

- preload首次>200 µm在19.533333 s，杯底相对漂移247.490 µm，杯世界转.332076°、actual hand仅.000829°。刚执行19.516667→19.533333的nominal目标相对EXTRACT起点仅ΔXY=[−2.127,+.083] µm、Δz=9.524 µm；decision为hold。杯底仍有来源支撑，间隙+.338 µm、environment竖直力.16494 N。
- 19.533333→19.550000才产生ΔXY=[−19.840,−2.524] µm和第4次33.333 µm预载收紧，是对已观察杯偏移/低力的反应。初始杯偏移不能由这条未来动作倒推为其原因；它对后续旋转有无贡献仍需单因素对照。
- sourcehold首次越界18.962500 s同样处于18.950000→18.966667区间，其先行nominal ΔXY仅[−.344,−.020] µm；约20 µm反应在下一区间才出现。

preload首越界时杯世界ΔXY=[+233.121,+32.082] µm，actual TCP仅[−3.130,+1.738] µm，command FK角变化.000117°。杯在来源支撑下发生被动相对运动，比“EE大幅转动或横移带动杯转”更符合记录，但尚未隔离接触力矩、初始姿态、摩擦和接触重分布的贡献。environment向上支撑力大于或小于mg均不能单独证明离架；应同时看实际来源间隙和接触。

## grasp04的评分起算边界

grasp04首lift指令始于21.15 s，原持续双侧参考在21.220833 s才形成，较指令晚70.833 ms。其最初杯世界转约.31°、相对将来参考的杯底差约267 µm发生于原参考形成前；该段只能作上下文，不能追溯改写旧标签。原参考形成后的本0.6 s前缀最大杯底漂移仅2.188 µm，完整原指标2.698 µm，原grasp_success=true仍保留。

因此不能把grasp04通过解释为“与teacher同一起点完全无初期摇摆”。固定前缀没有teacher truth XY反馈却仍出现初期约.31°杯转，也不支持把truth XY反馈视为初始摇摆的必要条件。完整任务仍false/诊断资格、BCfalse。

## 接触高度、形状与初始姿态

三条记录首触TCP均约.796 m；以首左指接触为例，preload相对sourcehold的实际TCP差[−.599,−.945,−.358] µm、姿态差.000242°；grasp04差[−1.652,−.815,−1.907] µm、姿态差.002569°。差异很小，不是30 mm抓高差；generic的.826 m是接近路点。

首右触点cup-local z≈39.88 mm，首左≈58.63 mm，均为band1侧壁cell00/02/10/12/20/22，距顶部band2起点67.221 mm至少约8.59 mm。首触cup-local |normal_z|最大.00550，约.315°小侧壁/角部法向；没有杯口斜面或上凸沿pair证据。回调法向按原collider顺序保留，不能直接当独立标定的受杯压力方向；有效cooked hull仍未独立认证。

三者首次左接触时TCP向下轴距严格竖直约.0545°；这是一个可检验的预接触姿态小差异，不足以单独解释1.75°，也没有反事实运行证明修正会有效。若后续需排除初始对齐影响，可在手指未接触时采用明确水平/竖直的既定抓取姿态做单因素对照，保留yaw/抓高/物理和全部验收门槛。延长名义朝向保持不是新增干预，因为EXTRACT已经如此。

当前v4只冻结EXTRACT XY可用于检验后续反馈的贡献，结果必须按新独立闭合证据判断，不能预期其必然消除首次200 µm越界。不得重置原抓持参考、放宽200 µm/1°或改写旧结果来使流程通过。

[紧凑JSON与来源SHA](summary.json) · [原姿态时序/CSV](../teacher_preload_01_orientation_review/summary.json) · [接触normal/高度与具体pair](../teacher_preload_01_orientation_review/contact_normal_height.json) · [实际预载4tick与评分复算](../teacher_preload_01_preload_audit/summary.json) · [三轮force/opening对照](../teacher_preload_01_force_compare/summary.json) · [H5/normalfailure/无损归档](../teacher_preload_01_closed_read_archive.json) · [固定源码契约审查](../preload_control_v2_contract_review/README.md)

无新增GPU/API、runtime/阈值/原数据/标签改动；所有坐标仅有权限的离线诊断，不输入policy。preload01原taskfalse/GRASP_SLIP、postretreat unavailable/null保持。
