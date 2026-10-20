# Env_v1 数据接口与读取验证

本目录记录数据链路的实现和已执行验证。没有训练模型，也没有把历史失败改成成功。当前历史回归验证不计入 Env_v1 新采集的成功/失败数量。

## 正常读取

`MinimalPickDataset(..., sample_filter="success"|"failure"|"all_valid")` 现在直接支持一个完整 episode H5 文件，也支持 `episode_data.hdf5` 分组格式。默认 `success` 保持旧 ACT/Diffusion 配置兼容。

- `success`：新记录必须 `complete=true`、`record_valid=true`、`task_success=true`、`eligible_for_success_bc=true`。旧版本只保留原有 complete+success 筛选语义，旧 success 不代表经过本轮重新物理验收。
- `failure`：必须为完整、明确有效的物理任务失败，`task_success=false` 与 `eligible_for_failure_analysis=true`。几何预检、初始化无效、物理无效、模型错误和进程中断不计入。
- `all_valid`：读取 `record_valid=true` 且任务结果明确的记录。仍通过 `episode_metadata` 和样本 `labels` 暴露结果，不能把整个集合当成功 BC 数据。

历史 false 标签没有 `record_valid` 证据时会保留 unknown，failure/all_valid 都不会自动收录。没有创建临时假成功索引，也没有改写任何原始 H5。

```bash
/home/wujing/Desktop/vla/labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py EPISODE_OR_INDEX.h5 --sample-filter failure --policy-type act
/home/wujing/Desktop/vla/labutopia-env/bin/python scripts/read_lab_cuvette_env_v1_data.py EPISODE_OR_INDEX.h5 --sample-filter all_valid --policy-type dp --n-obs-steps 3
```

新策略读取配置为 `policy/config/task/lab_cuvette_env_v1_act.yaml` 和 `lab_cuvette_env_v1_dp.yaml`。它们是已有读取器的配置，不表示训练已执行。

可选 `split_group_keys` 根据实际 H5 属性按条件分组；当前 Env_v1 配置使用 `source_slot_id`、`target_seat_id`、`scene_version`、`asset_version`、`task_type`。`condition_group_actual_inspection.json` 已只读核验真实 RPC Astra 与 extract01 记录：四组 ACT/DP 普通 batch 的动作及双视角 RGB 与保存值一致，false 标签和文件 SHA256 不变。每个文件只有一个条件时，非零验证比例明确报错，不能以同条件 episode 充当条件外 holdout；`val_ratio=0` 仍能正常读取。这五个键并未编码每种布局、物理或控制参数，不代表所有场景条件的唯一标识。

## 采集契约

`data_collectors.lab_cuvette_env_v1_collector.LabCuvetteEnvV1Collector` 复用现有流式 HDF5/录像基础类，控制器无关。生命周期：

```python
collector = LabCuvetteEnvV1Collector(cfg, output_dir, scene_contract=contract, camera_meta=cameras)
collector.begin_episode(0, initial_position, episode_id=episode_id, metadata=metadata)
collector.cache_transition(state_before, action, state_after, result)
labels = collector.finish_episode(result, independent_score=score_dict_or_path)
```

观测必须含 `joint_positions` 九维、`simulation_time`、`camera_data` 两个真实相机 `side_camera_rgb`/`wrist_camera_rgb` 的 CHW RGB uint8。`episode_id` 不匹配时拒绝，避免接收旧 episode 的动作。`debug` 进入独立 `privileged/*`，默认不进视觉策略输入。

动作保存原始 `raw_output`、完整 `command_q` 九维、双指 effort 上限、请求的夹爪目标、转换说明和推理墙钟耗时。兼容的八维 `agent_pose/actions` 明确为七个机械臂关节角(rad)+左指位置(m)，不能将八维速度或其他模型语义直接当成这套位置命令。右指与完整九维命令单独保留。

独立判分输入至少为 `episode_id`、`task_type`、`task_success`、`record_valid`、`geometry_valid`、`failure_type`、`termination_reason`。缺少判分时结果为 unknown，不接受控制器自报 SUCCESS。诊断子任务即使自身成功，也不能成为完整 loading 成功 BC。无真实标定声明。

H5 同步保存配置、场景契约、相机元数据、实际前后状态、原始/执行动作、阶段、时间及独立结果。相机旧键是同一 H5 内的 hard link，不是外部绝对路径或用另一视角伪造腕部图像。

## 已执行证据

- `historical_success_ACT_read.json`：真实 demo03 固定第0条成功数据 3705 步，正常 ACT 构造器、首/中/末批次，逐值检查动作与 RGB。
- `historical_success_Diffusion_read.json`：同一历史数据通过正常 Diffusion 读取，含三步观测历史、动作对齐和末端 padding；不是新版本任务成功。
- `minimal_pick_regression_read.json`：原 minimal_pick 真实518步数据的读取回归。
- `historical_unknown_failure_exclusion.json`：demo04 第1条真实滑移诊断失败和第3条几何停止保留原始 false 标签；缺少新有效性元数据时被正常筛选器排除。几何停止没有计作物理插入失败。
- 33项CPU单元/契约测试通过，验证历史默认行为、筛选、九维命令、双指 effort、未知判分、错误类别、episode 隔离、接触锁存、相机配置、接触区域、指令FK底部计算及debug深度的非有限值保留；测试 fixture 明确不是仿真实验。见 `current_cpu_contract_results.json`。

## 新环境实际读取与运行限制

`new_preview03_ACT_read.json` 与 `new_preview03_Diffusion_read.json` 已对新环境真实2秒预览记录的120个转换完成正常 `all_valid` 读取，首/中/末 RGB 与动作逐值一致。标签保持 `task_success=false`、`record_valid=true`、两种完整loading资格均false；这是预览物理记录，不计入完整loading成功或物理任务失败数量。该次进程在记录收尾后出现真实相机清理异常；数据可读不代表进程干净退出。

`new_preview03_portability_check.json` 检查所有H5链接、虚拟数据集和外置存储，未发现外部数据依赖。原始记录未修改。

`TCP_frame_audit.json` 从安装的Lula URDF核实：`panda_hand` 与默认IK `right_gripper` 的朝向相差180°，TCP位置在手局部Z+100mm。新物理采集器在初始化时再用实际求解器FK核对配置，避免把手坐标四元数直接当IK目标导致无意旋转。

`minimal_pick_regression_command_check.json` 是运行前只读检查，未启动Isaac。之后根任务已实际执行原专家回归：`outputs/lab_cuvette_loading/Env_v1/minimal_pick_regression_20261021_01` 真实518步、抬升111.84mm、双指保持1秒，原任务结果为SUCCESS；其新的正常ACT/DP读取证据为 `minimal_pick_actual_regression_ACT_read.json` 和 `minimal_pick_actual_regression_DP_read.json`。它证明原抓取与读取回归，没有作为器皿装载成功。

`preview04_inspection_v2/inspection.json`、`grasp01_inspection/inspection.json`、`grasp02_inspection/inspection.json`、`grasp03_inspection/inspection.json` 保存实际新记录的H5动作/后继状态、时间、全部双视角视频解码及正常读取检查。四者均不是完整loading成功；preview04为预览，grasp01/02接近控制失败，grasp03到达抓取阶段后抓取失败，原false结果保留。grasp03腕相机authored挂载固定，但实际画面仍缺少应能看见的器皿，不能因无黑帧和元数据存在就判视觉可用。

`scripts/audit_env_v1_tcp_fk.py` 只用安装URDF/XML/NumPy/SciPy复核实际关节和TCP，不启动Isaac。grasp02和grasp03同物理步关节FK与记录PhysX TCP最大差分别0.574µm和0.627µm，排除厘米级误差源自TCP帧读取。grasp03固定RESET目标的指令FK位置不再漂移，但这不代表物理标定精度；完整结果见 `grasp02_inspection/independent_URDF_FK_audit.json` 和 `grasp03_URDF_FK_audit.json`。

`grasp04_inspection/inspection.json` 实际1051个转换通过正常读取、动作/后继和标签一致性检查，独立结果为 `grasp_hold` 子任务成功。`grasp04_task_scope_filter_check.json` 核实它只能进入 `all_valid`，不能进入完整loading的成功BC或物理失败配额。器皿当时仍在来源支撑中，不能把该保持记录称为已拔出搬运。

相机问题已进一步用官方 `CameraParams` 与 `distance_to_image_plane` 诊断：preview05实际渲染投影仍是默认50/20.955镜头，而USD属性和读取K已改变。preview06将焦距/口径同步规范到原生USD常用数值范围并在传感器创建前写入；实际渲染P00已分别变为side=0.90670484、wrist=1.14531143，与所声明K一致，终帧实际腕图可见完整架体。二者是合成相机配置，没有真实光学校准。

`preview06_camera_startup_audit.json` 测得第一帧渲染器位姿为旧姿态，之后落后一个控制周期。初始4次、每周期2次无额外物理步的 render 只修复了 extract01 初帧：`extract01_renderer_USD_dynamic_audit.json` 显示945帧中后续944帧渲染器位姿仍匹配上一控制观测的USD位姿，当前位姿最大残差0.9663mm，末帧0.1995mm。因此旧 extract01 不能宣称动态图像与当前物理状态完全同步。

随后按安装版本官方 `isaacsim.exp.base.zero_delay.kit`，在应用启动时同时设置 `/app/hydraEngine/waitIdle=true` 和 `/app/updateOrder/checkForHydraRenderComplete=1000`，不增加物理步。`extract_fixed01_inspection/renderer_USD_sync_audit.json` 核验新的 extract_fixed_orientation01：两项实际设置在全部935帧生效，腕相机935/935帧渲染器位姿匹配当前USD位姿（位置最大残差6.7e−16m）；旧记录保留。检查方法和源码依据分别见 `scripts/audit_env_v1_camera_sync.py`、`installed_render_sync_source_audit.json`。这是软件渲染状态关联的修复，不是实物定位精度或真实相机光学校准。

`extract_fixed01_inspection/inspection.json` 已实际解码两路录像并检查首、中、末图像、零黑帧、传感器时间及普通ACT/DP读取。腕视角可见架体、器皿与夹指；全景中的来源架/器皿仍有部分被Franka遮挡且像素较小，不能只凭全景判定微小接触。depth大数组仅存于输出的 `camera_debug` 首末NPZ，策略默认观测仍是RGB和机器人状态。

`extract_fixed01_inspection/terminal_video_and_public_contract_actual_check.json` 核验三路原生录像均469帧，末帧15.6s与H5后继状态终点一致；收尾强制补入未到常规30Hz采样点的实际终帧，逐帧仿真时间保存在 `video_timestamps.json`。MP4仍为固定帧率，不能从其帧索引推断最后一个间隔。该记录还核验新的实际IK缓存命中字段（510次命中、425次报告调用求解器）；公共相机元数据白名单对真实保存元数据的CPU检查不等于实时RPC测试。

`extract_continuous_latch01_inspection/inspection.json` 检查后续真实2537步、42.3s记录：实际取出和搬运被独立判分观察到，但末3秒世界位置漂移230.445µm超过原200µm门槛，故 `task_success=false` 原样保留。正常ACT/DP `all_valid` 读取通过，完整loading的成功/失败资格仍均false；未插入、未松爪、未撤离。双路2537个传感器帧均有效，动态渲染姿态2537/2537匹配当前USD。`selected_extraction_transport_frames.jpg` 为同一运行的轻量代表帧；`terminal_video_and_selected_frames_actual_check.json` 核验三路native录像各1270帧、末帧42.3s与H5终点一致，并保留末段稳定窗口的失败数值。

`preinsert_continuous_latch01_inspection/` 保存后续真实4958步、82.65s预插入诊断的实际检查。其独立 `task_success=true` 仅表示架内抓取、清槽、搬运、安全接近和向上回抬通过；最近的实际器皿底部仍高于座口1.005962mm，未插入、未松爪、未执行装载后的夹爪撤离。最后规定1秒诊断保持漂移0.4835µm；独立3秒 `terminal_window` 包含主动回抬，不被冒充稳定放置窗口；`post_retreat_window` 仍 unavailable。普通ACT/DP `all_valid` 可读，完整loading `success` 和 `failure` 均明确排除，H5读取前后SHA256不变。双路各4958个有效唯一传感器帧、4958/4958当前渲染姿态匹配；三路native视频各2480帧、实际终帧82.65s与H5一致。`selected_safe_approach_retract_frames.jpg` 是同一运行的轻量代表帧；JSON保留原始独立结果与上述范围。

`replay_astra03_01_inspection/` 检查正式主入口的15步已执行关节命令回放：与原Astra03记录九维命令逐值一致，两个H5读取前后SHA256不变；普通ACT/DP、双视角和后继时间通过，15/15当前渲染位姿匹配。首个观测仍标RESET，之后观测标REPLAY；原阶段单独保存在 `actions_raw_json.source_phase`。这次回放不产生新模型推理，其独立结果仍为false/REPLAY_SOURCE_EXHAUSTED，不计完整loading任务失败数量。

终止时不足一个完整控制周期的记录只在显式terminated/truncated、正整数物理步且不超过名义控制周期时允许，实际间隔和partial标志逐行保留。正式新环境当前完成整个原子控制周期后结束；不会将时间间隔猜为60Hz。

## 格式导出核查

工程现有 `scripts/convert_labsim_data_to_lerobot.py` 使用旧 LeRobot API，默认回退60fps，并按帧索引降采样，不能据此证明本轮动作语义及时间转换正确；当前没有将其运行输出宣称为 Env_v1 合格转换。原始 HDF5 是权威记录，八维绝对关节位置不能自动标作 OpenPI DROID 的关节速度。实际模型 checkpoint 的动作变换需要在策略适配链路中逐项验证。

新增原格式便携导出命令，不修改动作、fps或标签：

```bash
/home/wujing/Desktop/vla/labutopia-env/bin/python scripts/export_lab_cuvette_env_v1_episode.py CLOSED_EPISODE_DIR --output NEW_PORTABLE_DIR --manifest-copy NEW_EVIDENCE.json
```

实际preview04已导出到 `outputs/lab_cuvette_loading/Env_v1/portable_samples/preview04_native_episode`，23个文件约53.96MB。H5复制前后SHA256相同，没有外部链接/VDS/外置存储；复制后的普通ACT和DP `all_valid` 读取通过。`preview04_portable_export_manifest.json` 保存全部文件哈希和真实读取结果，大H5不放进Git。导出包可独立读取记录，仿真环境、源资产和模型权重不在此数据包内；预览仍是预览，不能计作装载成功或完整物理失败配额。
