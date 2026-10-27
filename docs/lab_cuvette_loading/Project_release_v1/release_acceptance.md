# Project_release_v1 环境发布验收

本轮保持固定 standard 物理场景，验收同进程复用、记录闭合、正式策略接入和使用入口。策略是否完成装载与环境是否正确执行分别判定。本文会随本轮**实际关闭并读取后的证据**更新；进行中的实验不计通过。

## 冻结范围和证据口径

- 运行代码：`122c4c03586abdfa7e3117c13e62f8d46f786b04`。最终文档发布提交可能晚于运行提交；二者在交付清单中分开记录。
- 分支和实际 GitHub 默认分支均为 `codex/labsim`；`main` 保留上游。实际 CI 已通过，见 [GitHub 查询回执](validation/github_122c4c0_actual.json)。
- 资产：`Txie000/SLAI-Labsim`，revision `bb880f098180c291f6f65995f969d48047207067`。本轮未发布新资产；独立缓存实际下载并核对 83 项。[下载核查](validation/fresh_assets/manifest.json)、[逐文件检查](validation/fresh_assets/asset_check_actual.json)。下载耗时未保存，不补造数值。
- 10×10×67.5 mm 比色皿尺寸假设、20 g 质量假设；原 A 座 `candidate_far_hinge`、单台仪器、完整白色 6×6 架，来源 A1，其他器皿 F6。原座、接触材质、动力学、控制增益和独立评分门槛不变。
- 物理 240 Hz，控制/策略观察/采集 60 Hz；侧视和腕视原始传感器 640×480，公共策略图像 256×256；native 录像 30 Hz。主视角 1920×1080。相机配置见 [发布配置](../../../config/lab_cuvette_loading/Project_release_v1/standard.yaml)。
- 本机 Isaac Sim 5.1 / Python 3.11.16；`nvidia-smi` 实际为 RTX 4090、49140 MiB、驱动 560.28.03。只复用既有运行环境，无重装升级。干净 checkout 与独立缓存均在同一机器，未完成第二台机器验证。
- 同一 GPU 的 teacher 性能运行顺序独占；实际策略验收将一份 Isaac 与一份 π0.5 服务作为一个评测配对。未调用付费 GPT，不修改原预算账本。

## 核查后的分类

**已经运行的能力**：历史独立进程 teacher 装载、公共 EE/关节执行、GenericContactHold、双相机采集和 ACT/DP 读取继续保留。本轮 diagnostic 完整 teacher 再次成功，完整 H5 全读及正常 reader 已通过；短程 GUI 启动、物理交互、finish、关闭、读取已通过。它们不能替代同进程三集或长于历史 0.25 秒的真实模型验收。

**已确认并修复的问题**：旧采集器先发布 complete/index 再补资格，存在半成品入索引窗口；task 尾部相机/视频/结果关闭也必须纳入同一发布事务。新版先 prepared，等所有尾部成功才 commit；失败撤销当前集资格，不触碰旧集。重复 finish 幂等；旧 episode ID、观察和动作拒绝；正式 chunk 请求预留并缓存回执，部分执行不会重试补走。

**正在补的实际验证**：同一个 Isaac PID 的 teacher→提前结束→teacher，以及正式 RPC 的真实 π0.5 连续交互；结果以关闭后验收记录为准。

**保留到后续的事项**：第二台机器验证；真实质量、摩擦和仪器尺寸标定；全部实际 cooked collision 的完整尺寸反演；SDK 原生速度与位姿差分差异。它们不应被写成已完成，也不以本轮环境验收宣称实物精度。

## 数据闭合与复用

实现和入口见 [生命周期说明](lifecycle.md)。新版 H5 声明发布状态，并有唯一 finalization ID；H5、结果、完成标记、JSONL 索引必须一致。collector 只准备并关闭 H5，task 完成相机/终帧/视频/recorder/gzip/最终结果后才正式发布。尾部异常会把当前集撤回 incomplete，保留原评分与轨迹用于核查。

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

新版 `collect/eval` 保留每个 physics/contact UTF-8 字节，以 gzip level1 无损存储，并取消 collector 的第四路重复双视角录像；H5 图像和 native 三路录像不变。`diagnostic` 保留 plain JSONL 与额外录像。当前 eval 与 collect 的持久化规格相同，不宣传为无图像轻量模式。关闭收据保存每条流原始行数、字节数、SHA、存储体积及 EOF/CRC 验证；线上评分/安全采样没有降频。优化后的完整 teacher 测量正在进行，不预先给出收益。

## GUI 关闭：修复范围和残余

此前 `get_stage_state` 错误来自 USD context 已关闭后仍被菜单回调访问。发布入口在 context 尚有效时清理菜单，再调用正式 SimulationApp.close，未修改安装环境源码、未静默屏蔽异常。

本轮 `gui_finish_02` 短程实际退出码 0，原异常未复现，H5/gzip 和 ACT/DP 读取通过。但日志仍有 517 条 warning 和 2 条 shutdown error；`omni.kit.manipulator.prim.core` 的 `ManipulatorFactory` 只在 on_startup 局部导入，却在 on_shutdown 作为全局名字引用。API 返回成功不等于扩展内部无错误。安装源码、哈希、精确栈、时序及影响范围见 [实际关闭审计](validation/gui_finish_02_shutdown_actual_20261027/receipt.json) 和 [GUI 独立核查 v2](validation/gui_finish_02_closed/summary.v2.json)。后续更小的菜单清理方案尚未实现和验证，不列入修复成果。

第一次 `gui_finish_01` 因传入 CLI 未暴露的参数在启动前被拒绝，退出 2、未建 episode；已保留，不计任务失败。第二次按帮助中已有参数执行，无修改物理配置。

## 外部策略契约

完整说明见 [π0.5 契约](external_policy/contract.md)。使用本机既有 LIBERO SFT checkpoint，零样本指**没有在 LabSim 任务上训练**，不声称是未微调基础模型。固定权重/归一化 SHA。真实双相机及 8D 基座机器人状态进入原模型处理链；图像 224 保比例填充，原 quantile normalization 不重复应用。模型服务原输出、适配 EE 请求与最终 9D 执行命令分别记录。

模型 20 Hz，每动作 0.05 秒对应 3 个控制、12 个物理步；chunk=5，原 horizon=10 只选前 5。EE 迁移每轴限幅 0.5 mm/0.004 rad，夹爪正关负开转换为有界总开口。公共 EE、关节接口限幅并不数值相同。模型等待时暂停仿真；过期观察拒绝、重复完整请求返回原回执、部分执行丢弃旧 chunk。`target_reached` 为 TCP 1 mm/0.5° 的端点语义，不是插入成功或真实精度。

本轮计划真实交互上限 20 秒仿真、80 次模型推理、400 个动作；实际推理次数、执行量、终止原因与可读性在关闭后结果中记录。脚本零动作或受控异常测试单列，不计模型评测。

## 本轮实际入口与未完成项

本轮所有命令显式选择 `--project-version Project_release_v1`。省略仍默认 `Project_v1`，不能凭目录名字假定已启用新版。完整命令和支持状态见 [项目首页](../../../README.md) 与 [本版本入口](README.md)。模型、Isaac Python 分开，不修改已有环境。

干净 checkout `/tmp/labsim-project-v1-1-clean-20261027` 与独立资产缓存 `/tmp/labsim-release-v1-assets-20261027/bb880f098180c291f6f65995f969d48047207067` 实际使用；这些是本机出处，不是可移植安装路径。正式传输包使用相对目录，原始数据本机位置另列。

尚待闭合：连续三集物理验收、真实 π0.5 持续交互、其他短程终止类别、优化后完整测量与最终两份传输包。未完成结果不会以报告段落代替运行证据。
