# LabSim Project v1 1 项目发布与验证报告

日期 2026-10-27　面向 组内使用者 后续开发与评测人员

固定standard场景原计划teacher五条完整成功；另58da、9a、422、9a88各一条同源单次回归成功。GPT01–08八个不同调试均未完整装载；最新P9/GPT08实际抓持、离架和搬运，执行三次100µm下降后仍未建立目标定位、下降通行及承托证据，主动finish。正式评测未启动（已完成0/计划5）；预算未耗尽。

## 当前可用结果与验证范围

原座不变的固定standard场景，10×10×67.5mm尺寸假设器皿已有v7 teacher五条真实完整成功：各自由6×6来源架A1抓取、提取、搬运至candidate_far_hinge，插入、承托、松爪、撤离并观察三秒。五条原task/record/integrity/physics/BC均通过；real_calibrated仍false。

| 范围 | 实际已完成 | 结论边界 |
| --- | --- | --- |
| teacher原计划v7 | 5/5完整闭合；125.667秒/7539转换 | 固定standard确定性重复 |
| 额外同源teacher | 58da、9a、422、9a88各1条完整成功 | 4条单独回归；非9/5 |
| GPT01–08不同debug | 8条有效失败；0完整成功 | 4safety+4task；非正式成功率 |
| 最终P9与正式GPT | 08主动finish；同源teacher单条成功 | 正式已完成0/计划5；非0/5成功率 |

teacher使用仿真真值专家控制，与仅公开RGB、机器人和触觉的GPT评测分开。该成功不证明GPT会完成，也不把10mm假设反推为实物尺寸。原器皿对照、原座、历史失败和物理质量告警保留。

[teacher首条完整成功](../media/reading/teacher_support_align_01_full.mp4) · [同次成功释放撤离腕部局部](../media/reading/teacher_support_align_01_release_wrist_clip.mp4) · [GPT08完整主动结束主片](../media/reading/gpt_debug_08_self_state_incomplete_full.mp4) · [完整闭合范围与运行身份](release_snapshot.final.json)

## 连续执行修复与细位移诊断

原异常已零API确定性复现：Lula raw IK在两条前缀中分别跳1.975338/2.108210rad，但raw FK仍接近有效目标；逐关节post-clip后FK误差变9.282177/9.705014mm。未完整执行的raw解继续当下一seed，随后旧低层逐tick按实际TCP建立10mm局部目标，把有效目标带离原参考，约40mm请求最终实际位移213.732/230.539mm。已排除world/TCP坐标混用、四元数顺序和增量逐帧累加；Lula内部为何选远分支仍未知。

新执行器保持原请求目标，以局部连续IK、FK与关节步长界限预规划，实际跟踪和速度守卫执行。accepted只表示身份/边界/预检通过；execution_finished表示该动作生命周期闭合，含拒绝或partial；target_reached只指实际TCP终点容差；safety_stopped标安全/执行器/仿真守卫停止。旧completed仅表示循环结束，不证明到达或完整消耗请求区间。拒绝为0 tick/0时间；partial先查真实后继与回执，不能自动重放。

| 相同请求的异常动作 | 旧净位移 mm | 新净位移 mm | 新终点误差 µm |
| --- | --- | --- | --- |
| world 0 40 0 | 213.732 | 40.000868 | 1.527 |
| world 0 35 −19 | 230.539 | 39.823226 | 2.402 |

![两条原请求参数保持不变的异常前缀对照；终点误差与动态跟踪峰值分开。新动态峰值仍约0.367/0.251mm。](../diagnostics/final_fixed_prefix_02/comparison.png)

fixed_replay_02两集7动作到达且真实退出0；首次fixed_replay_01关闭后GC退出139保留。72个自由探针全部target_reached：最大终点误差12.87µm、控制边界路径误差峰0.30461mm，返回anchor最大位置误差17.97µm/姿态0.0344mrad。原native速度与差分速度差异保留。这是无接触控制边界诊断，不是接触精度或子步全路径保证。

另外24个空爪细位移对照：100µm目标由0/24变24/24，新版最大终点误差1.293µm、3秒保持整窗最大漂移11.529µm。与72自由探针分别统计；均未执行持物插入，不验证真实微米精度。

另以cd827ed零模型调用重放GPT05全部25个非ID请求，首次碰撞仍为49.908333秒的link6—SourceMesh5；11981物理行选定运动学字段相同，3项指力字段有小于0.48µN末位差，不能称全物理bitwise一致。显式上抬变式在累计59.864mm时link7碰同盖板停止，后续横移/等待未执行，不构成安全路线或GPT成功。

[原Lula跳解至目标重映射完整因果证据](../diagnostics/legacy_reproduction.md) · [全部7动作CSV](../diagnostics/final_fixed_prefix_02/action_comparison.csv) · [72自由探针](../diagnostics/free_space_checked_01/audit.json) · [24细位移A B原数据](../diagnostics/fine_preinsert_ab_20261027/summary.json) · [25动作闭合碰撞复现](../diagnostics/closed_trace_collision_repro_05/summary.json) · [显式变式实际partial及未执行项](../diagnostics/collision_clearance_05_02_collision_audit/summary.json)

## 完整teacher流程与可读成功数据

原计划v7五条实际runtime均0b922ec，固定来源A1与目标candidate_far_hinge，独立进程seeds0..4，首条GUI；各7539转换/125.666667秒，完整成功。另58da、9a、422、9a88各一条单次完整回归通过；最新9a88只跑了1条，不能说同提交跑5次或9/5。以下为首条代表，不把固定初态重复当随机泛化率。

| 实际事件 | 仿真时间 s | 独立证据 |
| --- | --- | --- |
| 双侧抓持 | 18.145833 | 实际两指接触 |
| 来源槽清出 | 20.850000 | 器皿实际底部离架 |
| 持物搬运 | 44.312500 | 实际水平位移≥50mm |
| 正确座内支撑 | 110.054167 | 原深度/对准/底力/inside同样本通过 |
| 双指张开脱离 | 112.191667 | 实测开口与零接触 |
| 实际撤离 | 116.416667 | 最小手爪—器皿净空40.034mm |
| 撤离后三秒 | 122.666667–125.666667 | 721物理样本，原稳定判据通过 |

五条H5各40个唯一dataset全读，183份受保护原文件SHA逐集不变；正常success过滤逐集读出ACT与DP batch，failure过滤拒绝。首条另验动作[3,16,8]、无ExternalLink/外部storage/VDS、替代路径读取。约1.944GB的单集H5仅给出处和SHA，不冒充已在小包或已完成异机部署/训练。

数据actions为7个绝对关节目标(rad)+左指目标(m)；9D实际命令另含右指且对称。wxyz四元数，obs在动作前、next state在物理子步后，间隔1/60秒；相机/状态独立时钟保留，严格同刻曝光未认证。GPT初始化每指effort上限8N；move/wait保留上一显式上限，gripper可选0至8N，不按teacher阶段/真值自动调力。记录是驱动上限，不是实测接触力。

[原计划五条真实审计](../diagnostics/teacher_standard_v7_closed_data_cohort_01.json) · [成功batch与数据自含性](../diagnostics/teacher_support_align_01_support_portability_audit/portable_success_acceptance.json) · [正常ACT DP reader证明](../validation/teacher_support_align_01_normal_reader.json) · [最终9a88单次全H5/便携回归](../diagnostics/teacher_p9_regression_01_closed_read_archive.json) · [同源完整事件与3秒原判据](../diagnostics/teacher_p9_regression_01_physical_timeline/summary.json) · [同源success ACT DP正常读取](../validation/teacher_p9_regression_01_normal_reader.json) · [同次成功释放撤离腕部LOCAL CLIP](../media/reading/teacher_support_align_01_release_wrist_clip.mp4) · [局部选窗与原SHA/事件QA](../media/reading/teacher_support_align_01_release_wrist_clip.receipt.json)

## 支撑交接修复及原门槛对照

v6实际已有底部支撑并完成开爪撤离，但OPEN时XY187.961µm超过原100µm，原TASK_INCOMPLETE保留。v7在SUPPORT_TRANSFER加入有界XY/姿态反馈，未连续满足原对准预算时暂停教师逻辑卸载clock，真实quiet和10秒watchdog仍按物理时钟。几何、摩擦、effort上限与独立评分不变。

![实际XY误差对各自SUPPORT起点；100µm线、各自OPEN线与原独立支撑点。v7中间振荡保留，未重采样成同一轨迹。完整tilt/底力三panel另链。](../diagnostics/teacher_support_v6_v7_comparison_20261027/teacher_v6_v7_XY_report.png)

v7首次correct_target_supported为110.054167秒：XY29.829µm、tilt0.070935°、深度27.000479mm、底力0.376174N；OPEN在112.016667秒，同帧XY5.581µm、tilt0.012933°、底力0.239238N及其余原门均通过。此后才实际脱指与撤离；最终三秒位置漂移0.420µm、姿态变化0.015113°。这些是声明范围内的仿真量。

支撑阶段264控制tick中80tick逻辑暂停，generic helper仍可能追赶原调度或回闭：26tick开口增加、8tick回闭。因此“暂停卸载时钟”不等于实测夹爪冻结。原NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT和NATIVE_TARGET_OVERLAP_UNAVAILABLE保留，有效cooked碰撞表面的全局误差仍未知。

GUI退出阶段有真实UI context=None回调异常，supervisor原退出0、数据闭合审计通过；准确日志片段单独保存，不宣称日志无错误。VERIFY末段腕视局部被裁出画幅，侧视目标小且有遮挡，成功不由末帧图片推断。

[完整XY tilt 底力三panel附件](../diagnostics/teacher_support_v6_v7_comparison_20261027/teacher_v6_v7_support_gate_comparison.png) · [报告宽图输入SHA与生成回执](../diagnostics/teacher_support_v6_v7_comparison_20261027/XY_report_figure_receipt.json) · [v6 v7图源与比较方法](../diagnostics/teacher_support_v6_v7_comparison_20261027/README.md) · [逻辑与实际开口CSV](../diagnostics/teacher_support_align_01_support_portability_audit/support_controller_actual.csv) · [真实GUI退出警告与限定](../diagnostics/teacher_support_align_01_support_portability_audit/GUI_shutdown_warning.json) · [v6原失败腕视局部对照](https://github.com/zez2001/LabSim/blob/9a4713cf8c71bed4d697625ab052b378608780cc/docs/lab_cuvette_loading/Project_v1_1/media/teacher_baseline_close_01_support_release_wrist_clip.mp4)

## GPT实际进展与未完成原因

| 不同debug | 决策 / 请求 / 终点t 秒 | 原失败分类 |
| --- | --- | --- |
| 01 / 初始提示 | 11 /11 /24.833 | SAFETY_COLLISION |
| 02 / prompt v2 | 33 /33 /59.867 | SAFETY_GEOMETRY_VIOLATION |
| 03 / prompt v3 | 15 /15 /29.667 | SAFETY_COLLISION |
| 04 / prompt v4 | 51 /51 /114.717 | GRASP_SLIP |
| 05 / P6 temporal | 25 /25 /49.917 | SAFETY_COLLISION |
| 06 / P7 detail | 17 /18 /36.017 | TASK_INCOMPLETE |
| 07 / P8 active view | 46 /46 /90.017 | TASK_INCOMPLETE |
| 08 / P9 self state | 34 /34 /65.117 | TASK_INCOMPLETE |

![GPT08 decision33实际side全幅JPEG，原双图与P7细节均保留。此时杯和手可见，但模型不确认整手下降通行、入座深度与承托；主动finish未宣称完成。](../diagnostics/gpt_debug_08_perception/gpt_control/observations/decision_000033/side_camera.jpg)

GPT04的TCP到达未保证器皿同步下降：座口正冲量后出现相对漂移，未记录分类座底支撑≥0.1N。GPT05在49.908333秒先发生link6—SourceMesh5碰撞，随后才超过200µm；当前可见升起盖板与碰撞网格变换一致，不能因旧整机高度估算把接触判为虚空。回调力仍未经独立实物标定。

最新GPT08运行P9：34决策/34请求、33物理动作加finish，3906转换/终点65.116667秒。15.6125秒抓持、17.670833秒离架、41.220833秒持物搬运；无原生禁碰或抓持越界。D30–32三次−100µm/0.2秒请求完成，实际TCP Z为−114.323/−100.732/−99.897µm，控制边界pathmax68.263/5.178/0.783µm；不是子步全路径或器皿插入精度。

最新08仍停留于稳定搬运：离线CAD/真实末态推导杯底高于原座口83.652mm、底110.652mm，对原A轴XY34.993mm；最后三动作杯底合计下降0.314892mm。该特权事后量未送模型，原depth/gap/inputoverlap仍null、底力0。模型因双图不建立通行、深度/承托主动结束，未释放/撤离。八条原task false、record/integrity/physics true、BC false、post-retreat unavailable/stable null均保留；本轮最远座口接触来自旧04，随后滑移。

[八条不同调试真实分类](GPT_closed_cohort.final.json) · [08实际公开输入范围](../diagnostics/gpt_debug_08_perception/summary.json) · [08各实际阶段双图/未到阶段](actual_model_stage_images.final.json) · [08全H5/正常failure读取](../diagnostics/gpt_debug_08_closed_read_archive.json) · [08同次完整阅读主片](../media/reading/gpt_debug_08_self_state_incomplete_full.mp4) · [08末态离线几何及原null](../diagnostics/gpt_debug_08_terminal_geometry/summary.json) · [08剩余三项未建立证据](../validation/gpt_debug_08_remaining_blockers_20261027/summary.json) · [三次100µm实际TCP回执](../validation/gpt_debug_08_remaining_blockers_20261027/D30_D32_comparison.csv) · [旧04座口滑移完整对照](../media/reading/gpt_debug_04_rim_obstruction_full.mp4)

## 公开观测边界与最终GPT尝试

公开finger_contact_N是按器皿身份过滤的双指法向范数，不是全物体触觉、摩擦或座底支撑。P9实际08已使用机器人自身状态与通用接触提示；看清杯和手、双侧保持接触或TCP到达，都不直接建立整手路线、自由入座或底部承托。

P9在P8上追加机器人自身CURRENT JSON及通用接触推进提示，非单因素A/B。它由公开q7和actualTCP求名义FK，给link6/link7/hand位姿与authored INPUT局部盒；runtime不读障碍/器皿/座位姿，不提供距离、规划或自动动作。盒不含手指、持物、cooked、接触偏置或扫掠体。08使用该输入后仍原TASK_INCOMPLETE，不能把自身几何信息当全局安全证明。

| 截至08闭合的固定共享前缀 | 数量或估价 |
| --- | --- |
| GPT08真实episode | 34决策/34请求；估价$3.050670 |
| 累计前缀 | 333尝试；$27.894200占用 |
| 已知usage / 未知预留 | $26.485230 /$1.408970（8次） |
| 相对$30上限剩余 | $2.105800；未耗尽，不是供应商账单 |

原finish立即结束采集并关闭进程，接口不支持同episode续跑，不能暗中重放或用teacher/真值接续。剩$2.1058未耗尽；未解决视觉定位/深度和安全通道之前停止重复reset。P9绑定760项CPU通过/13skip、Git-free82、独审130和CI43成功，实际同源teacher单次也通过；均不能替代GPT完整任务。原$30/1500网络请求、80k输入、1024输出、160模型调用不提高。

[P9冻结源码与CPU结果](../validation/public_robot_self_state_p9_20261027/change_audit.json) · [P9独立130项审查](../validation/public_robot_self_state_p9_independent_review_20261027/review.json) · [自身名义模型兼容边界](../validation/public_robot_self_geometry_p9_frames_20261027/compatibility.json) · [闭合06/07反事实输入上界](../validation/public_robot_self_state_p9_20261027/closed_06_07_bounds/summary.json) · [333条固定费用前缀](../diagnostics/gpt_debug_08_perception/ledger_episode_and_closed_prefix.json) · [finish关闭与无同episode resume](../validation/gpt_debug_08_remaining_blockers_20261027/continuation_interface_audit.json) · [双图未建立通行/深度/支撑](../validation/gpt_debug_08_remaining_blockers_20261027/README.md) · [杯筛选法向触觉的范围](../diagnostics/public_tactile_vector_feasibility_20261027/review.json) · [0API局部held诊断 非模型成绩](../diagnostics/active_view_probe_06_01_held_motion/summary.json)

## 运行与发布信息

长期分支codex/labsim。最新GPT08与额外teacher真实runtime均9a88ea0，CI43 completed/success；原计划teacher五条为0b922ec，四次额外回归分列。历史资料/媒体LFS提交487b282不替代运行代码身份。9a88的52项共享源码、17项物理依赖与旧资产/选定旧输出保护已核；不声称全部ignored历史输出有全局快照。最终交付提交由推送后真实包清单记录。

```bash
export LABSIM_ASSET_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/labsim/assets"
LABSIM_ASSET_REV=bb880f098180c291f6f65995f969d48047207067
./labsim assets download
./labsim assets check --asset-root "$LABSIM_ASSET_CACHE/$LABSIM_ASSET_REV"
./labsim doctor --json

./labsim eval --project-version Project_v1_1 --scene standard \
  --backend teacher --episodes 1 --gui \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_NEW

# P9显式版本；--dry-run仅打印，实际运行时移除
LABSIM_POLICIES=config/lab_cuvette_loading/Project_v1_1/policies
LABSIM_PROFILE=cubence_gpt6_context2_640high_temporal_detail_active_view_self_state.json
./labsim eval --project-version Project_v1_1 --scene standard \
  --backend gpt6 --episodes 1 --max-calls 160 --headless --dry-run \
  --provider-config "$LABSIM_POLICIES/$LABSIM_PROFILE" \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_P9_NEW
```

| 使用与边界 | 当前验证 |
| --- | --- |
| teacher原计划/额外回归 | 0b固定5/5；58da/9a/422/9a88各1条通过 |
| GPT/正式五次 | 八次不同debug无完整成功；正式未启动0/计划5 |
| 数据读取/记录资格 | 成功与有效任务失败ACT/DP通过；诊断不进BC |
| 资产/样例 | HF固定资产pin；旧Project1样例不冒充本版数据 |

需要已有Linux/Isaac Sim 5.1/Python3.11/NVIDIA环境，凭据仅环境变量；详见版本README。省略--project-version仍走旧Project_v1。teacher原计划五个--episodes 1独立进程，示例只演示单集，无随机化/训练。阅读包保留当前报告、关键证据与四段阅读媒体（teacher full/同次near、04失败、08未完成），大H5/raw与环境不随包；正常dataset-check成功/失败操作见usage，保留repo相对层级。

[版本入口、资产与P9操作命令](../README.md) · [正常reader/失败资格与部署](../usage.md) · [9a88实际CI43成功](../validation/CI43_actual_9a88ea0_20261027.json) · [9a88物理/旧资产/选定历史保护](../validation/runtime_source_equivalence_9a88ea0.json) · [四段当前媒体来源与SHA](reading_media_index.final.json) · [完整/局部与模型输入范围](media_scope.final.md) · [P9自身信息与未认证边界](../public_robot_self_state_p9.md) · [固定HF资产入口](https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067)

### 验证范围与限制

原计划五条固定standard确定性teacher及四条额外单次回归分列；最新9a88只回归1条，不说同提交5次/9of5或随机泛化。没有训练或硬件精度结论。

GPT八个不同调试均未完整装载，正式0/计划5未启动；不得写0/5正式成功率或把teacher成功换成GPT成功。

实际08的100µm请求是公开TCP控制边界量，未到座口/预插入口，不认证器皿插入精度；原depth/gap/inputoverlap未知保持null，post-retreat unavailable/stable null。

特权离线CAD/pose只用于判分分析，未送模型；输入mesh/hull/自身盒不等于cooked或连续全路线证书。

公开触觉为杯过滤法向范数，不是全物体触觉/摩擦/底部支撑。独立相机/状态时钟保留，严格曝光同刻未认证。

全部公开JSON/exactJPEG、静态prompt/schema及工具回执不等于完整HTTPbody/全部memory/private reasoning；返回model名称不能独立验证上游实现。

10mm尺寸/20g质量为工程假设、real_calibrated=false；两个native qualityflags、GUI退出warning、全局cooked误差及真实力标定未知保留。

阅读完整片保留全帧时序但有损；teacher腕近景是同次成功LOCAL CLIP，不能当GPT输入。H5/raw不随包；final package需按实际提交、相对目标、媒体SHA和总字节再核。

预算截至08为333尝试/$27.894200，已知估价与8次未知预留分开，剩$2.1058未耗尽；不是供应商账单。finish关闭后无同episode resume，不以回放/新reset冒充原尝试继续。
