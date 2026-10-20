# 先读：V0_demo04 第一次真实失败诊断数据

本页对应新执行的 `diagnostic_01/run/trial_00`，时间长 29.5 秒，共 1770 个 60 Hz 控制转换。终态为 `GRASP_SLIP_DURING_TRANSPORT`；源槽自然支撑、双指抓取和拔取已通过，运输资格未通过。记录实际到达阶段为 RESET、APPROACH_SOURCE、GRASP、EXTRACT、TRANSPORT。

本轮 `diagnostic_only=true`、`full_workflow_executed=false`，几何关口不通过。`success`、`workflow_success`、`data_eligible`、`full_task_eligible`、`full_success`、`native_pair_success`、`geometry_gate_passed`、`real_calibrated` 全部保持 false。没有 INSERT、放手、完整任务成功或真实校准结论。

## 完整 H5

工程相对位置：`outputs/lab_cuvette_loading/V0_demo04/portable_failure_01/episode_data.hdf5`。

文件大小为 **314,819,825 字节**，SHA256 为：

```text
8206d3d9f89c85dff71b198a7916a04fde2960bbf701debf460a6f8bcf3af8dc
```

根组 `episode_0000` 自含源 H5 的全部 52 个数据集：两路真实 CHW/RGB/uint8 图像各为 `[1770, 3, 256, 256]`，另含八维动作、前后状态、完整九维关节观测、时间、阶段、几何及接触诊断、独立判分和任务属性。辅助控制 `control_auxiliary/` 包含实际下发九维位置命令、每指 effort 上限、限幅前对称指位目标及 availability。完整控制调度以 JSON/SHA 保存，阶段字典包含 14 阶段并与 H5 编码字典一致。

逐项形状、类型和**全部逻辑值哈希**均与原 H5 相等，所有原 H5 属性原样保存。已独立确认没有外链、软链、虚拟数据集或外部存储数据集；溯源绝对路径只是字符串，读取 H5 的数据不需要这些路径。原始 H5 与源物理、配置和事件文件的 SHA 前后未变。

## 读取与核验

- `diagnostic_01_portable_audit.json`：导出器的完整数据集复制哈希、物理控制终点对齐和首次只读 batch 结果。
- `diagnostic_01_portable_independent_check.json`：独立检查自含存储、所有原属性、转换流长度、状态/时间连续性、真实图像、完整配置/14 阶段以及首段、中段、尾段和尾部 padding。
- `read_only_interface_review.json`：此前静态审查；其调度配置范围提示已在本次实际输出中核验解决。

现有 `MinimalPickDataset` 的正常成功筛选构造器明确拒绝本失败 episode。随后复用现有 `__getitem__` 与 `collate_fn` 做诊断只读，动作、图像和状态均逐值核对，末尾动作 padding 也已检查。临时诊断索引的标签仍为 false，读取后删除；交付 H5 不含该索引或任何外链。没有优化器、训练、推理或新的物理模拟。

`read_batch.npz` 仅为一个实际读取 batch；完整数据在上述 H5。八维动作未包含 effort 上限，物理重放还需配合完整九维命令和辅助控制，不能只根据八维 batch 推断物理重放或策略性能。

后续诊断若另有输出，将使用独立文件夹和独立证据，不覆盖本次失败记录。
