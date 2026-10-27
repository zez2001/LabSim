# Project_release_v1 环境发布验收

本轮保持固定 standard 物理场景，验收同进程复用、记录闭合、正式策略接入和使用入口。策略是否完成装载与环境是否正确执行分别判定。本文会随本轮**实际关闭并读取后的证据**更新；进行中的实验不计通过。本轮原生运行、闭合数据读取和真实策略交互已完成，长期资源稳定性仍有限制。

## 冻结范围和证据口径

- 物理与真实策略运行代码：`122c4c03586abdfa7e3117c13e62f8d46f786b04`；短程五类终止 CLI：`73b1a9db9470f9706a3068a8ce24e7e09d8cfc65`；正式 reader 修复与干净 checkout 读取：`4a716359376de0132cc83cba3e5c7d27c791069e`。最终文档提交晚于上述运行提交，交付清单分开记录；后两次只改 CLI 诊断选项和数据资格读取，未改仿真物理核心。
- 分支和实际 GitHub 默认分支均为 `codex/labsim`；`main` 保留上游。实际 CI 已通过，见 [核心运行 CI 回执](validation/github_122c4c0_actual.json) 与 [reader 修复 CI 回执](validation/github_4a71635_actual.json)。
- 资产：`Txie000/SLAI-Labsim`，revision `bb880f098180c291f6f65995f969d48047207067`。本轮未发布新资产；独立缓存实际下载并核对 83 项。[下载核查](validation/fresh_assets/manifest.json)、[逐文件检查](validation/fresh_assets/asset_check_actual.json)。下载耗时未保存，不补造数值。
- 10×10×67.5 mm 比色皿尺寸假设、20 g 质量假设；原 A 座 `candidate_far_hinge`、单台仪器、完整白色 6×6 架，来源 A1，其他器皿 F6。原座、接触材质、动力学、控制增益和独立评分门槛不变。
- 物理 240 Hz，控制/策略观察/采集 60 Hz；侧视和腕视原始传感器 640×480，公共策略图像 256×256；native 录像 30 Hz。交付原生双视角录像实际为 1280×480，不能把保留配置中的 main_resolution=1920×1080 当成交付 MP4 规格。相机配置见 [发布配置](../../../config/lab_cuvette_loading/Project_release_v1/standard.yaml)。
- 本机 Isaac Sim 5.1 / Python 3.11.16；`nvidia-smi` 实际为 RTX 4090、49140 MiB、驱动 560.28.03。只复用既有运行环境，无重装升级。干净 checkout 与独立缓存均在同一机器，未完成第二台机器验证。
- 同一 GPU 的 teacher 性能运行顺序独占；实际策略验收将一份 Isaac 与一份 π0.5 服务作为一个评测配对。未调用付费 GPT，不修改原预算账本。

## 核查后的分类

**已经运行的能力**：历史独立进程 teacher 装载、公共 EE/关节执行、GenericContactHold、双相机采集和 ACT/DP 读取继续保留。本轮 diagnostic 完整 teacher 再次成功，完整 H5 全读及正常 reader 已通过；短程 GUI 启动、物理交互、finish、关闭、读取已通过。它们不能替代同进程三集或长于历史 0.25 秒的真实模型验收。

**已确认并修复的问题**：旧采集器先发布 complete/index 再补资格，存在半成品入索引窗口；task 尾部相机/视频/结果关闭也必须纳入同一发布事务。新版先 prepared，等所有尾部成功才 commit；失败撤销当前集资格，不触碰旧集。重复 finish 幂等；旧 episode ID、观察和动作拒绝；正式 chunk 请求预留并缓存回执，部分执行不会重试补走。

**本轮新增实际验证**：同一 Isaac PID 1394458 的 teacher→提前结束→teacher 已完成；正式 RPC 的真实 π0.5 连续交互与自然安全停止已完成；五种额外短程终止全部运行并正常退出。关闭后的资格与数据读取分层核查见下文。

**保留到后续的事项**：第二台机器验证；真实质量、摩擦和仪器尺寸标定；全部实际 cooked collision 的完整尺寸反演；SDK 原生速度与位姿差分差异。它们不应被写成已完成，也不以本轮环境验收宣称实物精度。

## 数据闭合与复用

实现和入口见 [生命周期说明](lifecycle.md)。新版 H5 声明发布状态，并有唯一 finalization ID；H5 最终 attrs、task_properties.labels、qualification_json、collector 最终结果、task 最终结果、完成标记、JSONL 索引中的权威资格必须一致。原始 independent_score.json / H5 independent_score_json 是 collector 关闭前的独立物理评分快照，其中 record_integrity 可为 pending/null；保留该原始阶段记录，不将它解释为最终采集资格，也不事后改写历史轨迹。collector 只准备并关闭 H5，task 完成相机/终帧/视频/recorder/gzip/最终结果后才正式发布。尾部异常会把当前集撤回 incomplete，保留原评分与轨迹用于核查。

CPU 覆盖六种真实父类尾部故障注入、旧集保护、重复 finalize、多集索引、相对移动与正常 reader；[80 项 CPU 验证](validation/recording_termination_cpu.json)。这些是可控软件故障注入，不冒充磁盘损坏或真实服务掉线。

多集 relative HDF5 索引是来源 H5 的相对链接集合，**不是自包含单文件**。完整数据交接须一起移动来源目录，或显式使用 `--mode copy`。反馈包不携带多 GB H5，提供原位置、大小、哈希、生成和读取方式。

## 基线与必要优化

同口径基线来自 `baseline_diagnostic_01`，运行提交 `cbf8446`，单进程已退出：

- 仿真 125.6667 秒，7539 条 transition，完整装载成功。
- 启动 7.04385 秒，rollout 1129.26456 秒；父进程从启动到退出 1215.07025 秒。rollout 与完整进程墙钟不是同一个口径。
- 总输出 3,878,486,272 B：H5 1,944,570,883 B，录像 55,591,990 B，physics 1,236,569,165 B，contact 573,337,781 B，execution 64,178,079 B，其他 4,238,374 B。
- 40 个唯一 H5 dataset 全量解码 3,849,922,035 B，13.6251 秒。热 batch 中位 ACT 7.45 ms、DP 17.10 ms；不是冷启动部署延时。
- task finalize 0.41402 秒，其中 collector 关闭 0.06512 秒；不是全程写入或 Isaac 退出耗时。
- RSS reset 后约 5.057 GB、结束约 8.372 GB，采样 VRAM 3591 MiB，FD 338→339→334。单集增长不能单独证明泄漏；多次 reset 后趋势另查。VmHWM 为进程累计高水位，采样 VRAM 不冒充连续精确峰值。

原始小型证据：[基线 summary](validation/baseline_diagnostic_01_closed/summary.json)、[体积与性能 CSV](validation/baseline_diagnostic_01_closed/performance_measurements.csv)、[读取耗时](validation/baseline_diagnostic_01_closed/normal_reader_timings.csv)。H5 的 dataset storage 统计不含可变长 JSON heap，不能将文件差额直接判断为碎片。

新版 `collect/eval` 保留每个 physics/contact UTF-8 字节，以 gzip level1 无损存储，并取消 collector 的第四路重复双视角录像；H5 图像和 native 三路录像不变。`diagnostic` 保留 plain JSONL 与额外录像。当前 eval 与 collect 的持久化规格相同，不宣传为无图像轻量模式。关闭收据保存每条流原始行数、字节数、SHA、存储体积及 EOF/CRC 验证；线上评分/安全采样没有降频。同口径 episode 对比已经完成：3,878,360,980→2,327,380,401 B，减少 1,550,980,579 B / **39.9906%**；physics+contact 从 1,809,906,946→269,707,641 B，减少 **85.0983%**；录像 4→3 路，H5 体积基本不变。首 teacher rollout 1129.265→1086.598 秒，但第三集 teacher 为 1191.886 秒，不能承诺稳定提速。完整 H5 全读为 13.625 / 14.183 / 14.595 秒。参见 [同口径对比原始数据](validation/baseline_vs_collect_01_comparison/summary.json)。新版两阶段关闭的计时边界与旧版不同，不把差值当独立 writer 优化收益。

## 退出阶段：修复范围和残余

此前 `get_stage_state` 错误来自 USD context 已关闭后仍被菜单回调访问。发布入口在 context 尚有效时清理菜单，再调用正式 SimulationApp.close，未修改安装环境源码、未静默屏蔽异常。

本轮 `gui_finish_02` 短程实际退出码 0，原异常未复现，H5/gzip 和 ACT/DP 读取通过。但日志仍有 517 条 warning 和 2 条 shutdown error；`omni.kit.manipulator.prim.core` 的 `ManipulatorFactory` 只在 on_startup 局部导入，却在 on_shutdown 作为全局名字引用。API 返回成功不等于扩展内部无错误。安装源码、哈希、精确栈、时序及影响范围见 [实际关闭审计](validation/gui_finish_02_shutdown_actual_20261027/receipt.json) 和 [GUI 独立核查 v2](validation/gui_finish_02_closed/summary.v2.json)。同一 SDK NameError 也在本轮 headless 三集和 π0.5 关闭日志中出现，不局限于 GUI；见 [范围补充](validation/gui_finish_02_shutdown_actual_20261027/headless_scope_addendum.json)。后续更小的菜单清理方案尚未实现和验证，不列入修复成果。

第一次 `gui_finish_01` 因传入 CLI 未暴露的参数在启动前被拒绝，退出 2、未建 episode；已保留，不计任务失败。第二次按帮助中已有参数执行，无修改物理配置。

## 外部策略契约

完整说明见 [π0.5 契约](external_policy/contract.md)。使用本机既有 LIBERO SFT checkpoint，零样本指**没有在 LabSim 任务上训练**，不声称是未微调基础模型。固定权重/归一化 SHA。真实双相机及 8D 基座机器人状态进入原模型处理链；图像 224 保比例填充，原 quantile normalization 不重复应用。模型服务原输出、适配 EE 请求与最终 9D 执行命令分别记录。

模型 20 Hz，每动作 0.05 秒对应 3 个控制、12 个物理步；chunk=5，原 horizon=10 只选前 5。EE 迁移每轴限幅 0.5 mm/0.004 rad，夹爪正关负开转换为有界总开口。公共 EE、关节接口限幅并不数值相同。模型等待时暂停仿真；过期观察拒绝、重复完整请求返回原回执、部分执行丢弃旧 chunk。`target_reached` 为 TCP 1 mm/0.5° 的端点语义，不是插入成功或真实精度。

本轮预设上限 20 秒动作仿真、80 次模型推理、400 个动作，实际 **69 次真实推理、341 个动作、1021 个控制周期 / 4084 个执行物理步**；340 个动作完整执行，最后一个执行 1/3 周期后安全停止，剩余 chunk 的 4 个动作未下发。实际动作时间 17.0167 秒，含 reset 初始化的 episode 时间为 17.0333 秒。69 次推理前后仿真时钟不变；模型原返回、适配请求、9D 执行记录逐条核对。碰撞为 panda_hand 几何与 Instrument/Collision/SourceMesh2，任务没有抓取、清出或装载完成。结果为 SAFETY_COLLISION / safety，task_success=false，最终 record_valid 和声明范围的 physics_trustworthy 为 true，成功 BC 不合格，失败分析可用。首末真实模型输入/输出及逐次哈希、接触事件见 [真实模型全链路审计](external_policy/pi05_standard_01_closed_audit/summary.json)。原模型有 264 tokens 超过 200 上限的截断 warning，本轮未修改策略以优化任务。脚本零动作或受控异常测试单列，不计模型评测。

## 本轮实际入口与未完成项

本轮所有命令显式选择 `--project-version Project_release_v1`。省略仍默认 `Project_v1`，不能凭目录名字假定已启用新版。完整命令和支持状态见 [项目首页](../../../README.md) 与 [本版本入口](README.md)。模型、Isaac Python 分开，不修改已有环境。

干净 checkout `/tmp/labsim-project-v1-1-clean-20261027` 与独立资产缓存 `/tmp/labsim-release-v1-assets-20261027/bb880f098180c291f6f65995f969d48047207067` 实际使用；这些是本机出处，不是可移植安装路径。正式传输包使用相对目录，原始数据本机位置另列。

本轮同一机器分阶段完成资产下载检查、短 GUI demo、连续 collect、正式 dataset-check 和真实 RPC policy eval。运行代码与读取修复提交分别给证据，不将其写成第二台机器的一键部署验证。最终两包清单、媒体来源、发布 SHA 与 CI 另见交付清单。


## 同进程三集、正式读取与时序

实际结果为完整成功、有效提前结束、完整成功，transitions 为 7539 / 180 / 7539。器皿、关节和夹爪初态的读取值一致；GenericContactHold、跟踪补偿、评分器和动作回执缓存重建。两次旧 episode 动作均拒绝，新增物理 tick 为 0。三份 UUID 唯一，finalization 标记一致，129 个原文件前后 SHA 不变。120 个唯一 H5 对象全读和 6 条 gzip 流逐字节解压 / CRC / 记录 SHA 核对通过。[三集闭合审计](validation/same_process_collect_01_closed/summary.json)。

必须区分两层读取：最初 42 项是底层 MinimalPickDataset 的 ACT/DP 读取，不代表发布版资格检查已通过。随后实际正式 CLI 暴露 controlled_lifecycle_diagnostic 不在白名单的问题，保留 [首次失败证据](validation/official_dataset_check/initial_cli_failure_observed.json)。提交 4a71635 仅在 release 中支持该组，v1.1 白名单不变，服务/执行/仿真错误与未完成记录仍拒绝。干净 checkout 正式 CLI 复验 ACT 与 DP 均为 success=2、failure=1、all_valid=3，[正式结果](validation/official_dataset_check_clean_4a71635/summary.json)。没有为适配 reader 改成功标志。

每条 transition 的后继为下一条观察、时间间隔为 1/60 秒。原传感器时间是 engine clock；扣除每集记录的 origin 后，两个完整 teacher 的最大时钟差约 6.55 微秒，是数值时间字段的检查，**不是实际图像内容逐像素同步或机械精度测量**。[全标量时序核查](validation/same_process_collect_01_transition_clock_actual.json)。

π0.5 的专用 index 仅选真实 episode_0000，正式 clean reader 的 failure/all_valid 各读取 1 集、ACT/DP 均通过。随后 10 个 0.05 秒零增量 reset 资源探针单独排除；它们不是 10 个策略评测或完整任务失败，不修改原始标签。[专用索引及排除说明](validation/pi05_standard_01_env_closed/curated_index_manifest.json)。

## 终止覆盖与重启

五项短诊断使用同一个额外原生进程 1754496，全部写完结果后退出 0。early_finish 为有效 TASK_INCOMPLETE；no_progress 在预声明 5 秒上限终止为 TIMEOUT；unreachable 在实际物理交互后提交超关节上限目标，被预规划零步拒绝，再主动结束。service_timeout 与 user_interrupt 是可控 TimeoutError / KeyboardInterrupt 注入，分别为 service 与 interruption 领域、task_success=null、record_valid=false，不能当有效任务失败或正常训练样本。实际模型自然安全碰撞另由 π0.5 episode 提供。每集保留后继观察、重复 finish、旧观察拒绝和录像关闭证据；[145 项闭合审计](validation/termination_cases_01_closed/summary.json) 与 [35 项最终权威资格核对](validation/termination_cases_01_closed/authoritative_fields_addendum.json) 均通过，15 路 MP4 完整解码；关闭前原始评分的 pending 字段单独解释。

关闭后实际启动了新的 Isaac 进程，未依赖 checkpoint/resume。process_exit.json 是父进程 Popen.wait 加实际 PID 已消失的证明；CLI wrapper 和真正 Isaac PID 分开核查。scheduler 的终态展示布尔可能陈旧，不能拿它覆盖实际退出证明。

## 资源遗留与后续边界

三集末 RSS 为 8.338 / 8.518 / 8.920 GB，第一至第三增加 582,193,152 B；FD 均回到 332，采样 VRAM 均为 3591 MiB。针对增长，真实 π0.5 后在同一 RPC 进程追加 10 次 reset + 0.05 秒零增量交互：RSS 从探针前 5.580 GB 到最终 6.081 GB，增加约 500 MB；首探针结束至最后增加约 368 MB，FD 332→334，VRAM 3627→3691→3627 MiB。它们全部可 finish/reset、最终进程退出，但没有证明长期内存平台化或排除原生缓存/对象残留。

本轮发布结论限于**实际完成的有限长度连续采集、失败后 reset 恢复、真实零样本接入、安全终止和正常数据读取**。退出 SDK 回调错误、长程 RSS 增长的具体归属、第二台机器复现仍是遗留项；不宣称无限期常驻稳定、真实仪器标定或精度认证。建议长批次暂按已验证的短 episode 组启动独立进程，并保留资源采样；这不是完整 checkpoint/resume。
