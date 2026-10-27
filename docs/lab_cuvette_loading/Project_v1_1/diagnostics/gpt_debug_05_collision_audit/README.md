# GPT05 高位 link6 禁碰的闭合离线归因

GPT05 在搬运途中以原 `SAFETY_COLLISION / ROBOT_ENVIRONMENT_COLLISION` 安全停止，未到入座阶段。首次原生禁碰是 **49.908333 s、physics step 11978，panda_link6 ↔ Instrument/Collision/SourceMesh5**。它不是器皿碰座，也不是 GPT03 的 leftfinger–SourceMesh2。原 task=false、record/integrity/physics=true、success BC=false、post-retreat unavailable / stable=null 保留；`independent_score` 原 collector_pending 快照不覆盖闭合 result 的完整性来源。

本审查在 process_exit 真证明、PID 1211605 已不存在后才读 GPT05。两份 gzip 全部流式扫描：65,189 条 native event、11,981 条 physics row；解压 SHA/字节与既有无损 archive 的原文件条目一致。不读 H5、不改原文件、不归档或重编码视频，不读取正在运行的 teacher。全部离线物体/接触/网格量都没有输入 policy。

## 碰撞事件与原护栏

[三个完整原生事件](native_forbidden_contacts.json)均为同一 pair，CONTACT_FOUND 后两条 PERSIST，无重复标记；整个 native 日志没有杯–仪器事件。首条六点中五点冲量为零，一点非零。故不把六个候选点统称六次有力碰撞。

非零点 world=(0.259312212, −0.165390253, 1.313000441) m，原 separation=−0.543088 mm。其余点高度延伸至 1.317000389 m。原 callback 保存 impulse=(−26.658073, −0.922806, −1.120236) Ns，按明确的 1/240 s 除得 raw force=(−6397.937622, −221.473403, −268.856678) N。**这些只是仿真接口原量，正反受力约定、幅值和实物力均未独立校准，不能称为可信真实接触力，也不与 tensor force 叠加。**

[运行版本护栏原文](runtime_guard_source.json)判定 robot/environment、非 cup pair，任一点 `norm(raw_force)>0.01 N` 或 `separation<−50 µm` 即禁碰；首条两分支都满足。因此这次有非零求解器冲量与负 separation 证据，超过单纯 AABB 或零冲量候选接触。PERSIST 点的 separation 回到接近零时仍有原非零冲量，详见原记录；不据此改写物理可信标签。

## 实际变换与输入几何

[几何提取](geometry_extract.json)使用该轮 config 的实际资产缓存和 recorded q9，CPU 组合 USD 变换、URDF FK；不启动 SimulationApp、IK、渲染或物理。七份 runtime 资产 SHA 与本轮 scene_contract 全相符，见[资产核对](actual_runtime_asset_checks.json)。用于重建的仓库 Franka/仪器与实际缓存字节相等；runtime 器皿清理派生 SHA 与旧仓库源分开记录，器皿位姿直接取本轮 raw。

SourceMesh5 的世界 row matrix 是 Rz(90°) 加平移 (0.36,0,0.74) m。实际 world AABB 为 [(0.259312384, −0.180250004, 0.948000004), (0.476742007, −0.032249998, 1.317000022)] m；authored approximation=none。不能套用先前另一整体参考姿态的 1.178 m 估计。六个原接触点到这个实际变换后三角网的距离为 0.172–0.419 µm，位置确在该高位盖板输入材料的边面/顶缘附近。

同一 after-step q9 的 link6 AABB 为 [(0.079255933, −0.202272032, 1.273301059), (0.261416888, −0.111070225, 1.406251187)] m。CPU FK 的 TCP 与本轮 raw actual TCP 位置差 0.294 µm；这只是计算一致性，不是实际精度结论。完整 11 个带碰撞几何 link 的变换、AABB 和最近三角面顶点保存在几何提取中；空 link8 明确不当作遗漏碰撞体。

[输入三角面 SAT 检查](input_surface_crossing_checks.json)在 49.900000、49.904167、49.908333、49.912500 s 的 sampled q 上，原 link6 材料面和重建 input convex hull 都与 SourceMesh5 顶部三角面交叉，保存了具体三角形证据。这表明本轮高位接近不必依赖“只有凸包填充才有的额外凸出”才能解释。**它不认证实际附着 cooked 表面、精确 native 碰撞起点或所有 cooked/input 误差。** callback 点和 after-step FK 处于不同求解时点，距离不能强行等同 raw separation；源 Franka link6 本来声明 convexHull。

## 动作和模型实际所见

[原 D22–24 工具/回执](public_actions_22_24.json)：D22 在 44.016667 s 发 world −Y40 mm/2 s；D23 在 46.016667 s 发 +Y40 mm/2 s，回到近同一 TCP。D24 在 48.016667 s 发 world +X35 mm/2 s，未改变名义姿态或高度。[原 partial receipt](last_partial_receipt.json)为 accepted=true、execution_finished=true、target_reached=false、safety_stopped=true：实际执行 114 tick/456 physics steps/1.9 s，49.916667 s 结束，剩余 TCP 目标误差 2.035609 mm。该余差包含安全提前结束，不能当失控位移。

六张 [D22 side](public_inputs/decision_000022/side_camera.jpg) / [wrist](public_inputs/decision_000022/wrist_camera.jpg)、[D23 side](public_inputs/decision_000023/side_camera.jpg) / [wrist](public_inputs/decision_000023/wrist_camera.jpg)、[D24 side](public_inputs/decision_000024/side_camera.jpg) / [wrist](public_inputs/decision_000024/wrist_camera.jpg)均为实际 640×480 q60/high exact JPEG，已逐张查看，复制字节未变。侧视可看到开盖与上方腕部在投影中接近，但不能确认 3D 整臂净空；腕视主要看杯、双指和下方腔体，未补足高位 link6–盖顶间隙。D24 另有 D23 stale wrist 和 D7 首次公开双侧接触参考 wrist，原 manifest 与两图/公开 JSON 一并保存；它们不是整臂碰撞包络。

按固定 side 相机把事后接触点离线投影约为 (391.61,115.46) px，仅帮助审阅定位，**不是同刻像素可见认证，也不是曾发给模型的标注或 GT crop**。不推断私有模型推理。该次尚无入座下降，P6 的 100 µm 接触区观察节拍没有被实际检验。

## 碰撞前后抓持与 GPT03 对照

[抓持时序](grasp_before_after_impact.json)使用原 14.1125 s cup-in-hand reference。首次禁碰前 body 漂移最大 1.839167 µm、配置 anchor 最大 1.446800 µm；第一次 body 超过 200 µm 出现在碰后下一子步 49.9125 s，为 706.716 µm / 0.696602°、anchor 70.765 µm。因此不能解释成碰撞前已滑脱；杯底参考包含旋转杆臂运动，也不把 706 µm 全称纯轴向滑移。原最终 grasp_success=false 保留。

[GPT03 对照](comparison_GPT03_GPT05.json)复用旧闭合审计、不重读旧 raw：03 在 29.654167 s 是 leftfinger–SourceMesh2，接触 z≈0.937800 m；05 是 link6–SourceMesh5、z≈1.313–1.317 m。共享一般的整臂/障碍净空问题，具体机器人 link、仪器 shape 和高度不同，不称同一碰撞根因或相同条件 A/B。

下一步可在单独诊断中重放同一末段前缀，核对实际 native link pose、attached cooked representation 和碰撞点，保持原物理/阈值；本审查不执行该步骤，不建议仅重复模型请求或放宽护栏。

[summary.json](summary.json) · [raw 扫描证明](native_scan_proof.json) · [逐样本 CSV](collision_window_physics.csv) · [原来源前后 SHA](source_SHA256.json)。分析脚本只保存本次 CPU 方法与命令路径，原运行/缓存路径为出处，不承诺阅读包中含大原数据。所有结论仅限声明输入几何和该闭合仿真记录，cooked 全局误差和实物标定仍未知。
