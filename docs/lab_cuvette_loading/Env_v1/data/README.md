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
- 13项单元/契约测试通过，验证历史默认行为、筛选、九维命令、双指 effort、未知判分、错误类别及 episode 隔离；测试 fixture 明确不是仿真实验。

## 格式导出核查

工程现有 `scripts/convert_labsim_data_to_lerobot.py` 使用旧 LeRobot API，默认回退60fps，并按帧索引降采样，不能据此证明本轮动作语义及时间转换正确；当前没有将其运行输出宣称为 Env_v1 合格转换。原始 HDF5 是权威记录，八维绝对关节位置不能自动标作 OpenPI DROID 的关节速度。实际模型 checkpoint 的动作变换需要在策略适配链路中逐项验证。
