# 先读：V0_demo04 已完成的有界预插入诊断数据

本页对应 `diagnostic_03/run/trial_00` 的本轮真实执行：**76.9166667 秒、4615 个 60 Hz 控制转换、18461 条含初态的物理记录**。运行墙钟为 222.501 秒。终态为 `GEOMETRY_BLOCKED_PREINSERT`，独立判分的 `diagnostic_subtask_completed=true`，10 项诊断检查全部通过。

实际阶段为 RESET、APPROACH_SOURCE、GRASP、EXTRACT、TRANSPORT、ALIGN、GATE_RETRACT、DIAGNOSTIC_HOLD，完成自然支撑、双指抓取、拔取、运输、受阻座入口上方受控停止、向上撤回和保持。`diagnostic_only=true`、`full_workflow_executed=false`；原座几何关口仍为 false，没有执行 INSERT、座内放置、放手及完整加载流程。

原 H5 的 `complete=true` 表示记录已经闭合，`diagnostic_read_eligible=true` 表示可以诊断读取。`success`、`workflow_success`、`data_eligible`、`full_task_eligible`、`full_success`、`native_pair_success`、`geometry_gate_passed`、`real_calibrated` 全部保持 **false**。有界诊断完成不代表原配套或完整任务成功，也没有真实校准结论。

## 用于阅读包的完整自含 H5

工程相对位置：`outputs/lab_cuvette_loading/V0_demo04/portable_01/episode_data.hdf5`。

文件大小为 **885,164,015 字节**，SHA256 为：

```text
65c32000917083544db3f881054dbf4706a606fcc368002332caf7ccf564e6b0
```

该 H5 的 `episode_0000` 组保留全部 52 个源数据集及原属性。两路真实 CHW/RGB/uint8 图像各为 `[4615, 3, 256, 256]`，并包含动作、前后状态、完整九维关节观测、时间、阶段、几何和接触诊断、独立判分及任务属性。`control_auxiliary/` 保存实际下发九维位置命令、每指 effort 上限、限幅前对称指位目标及 availability；调度 JSON/SHA 记录完整配置，14 阶段字典与 H5 编码一致。

全部源数据集的形状、类型和**全部逻辑值哈希**一致，全部原属性精确保留。没有外链、软链、虚拟数据集或外部存储。溯源绝对路径仅是字符串，H5 的数据读取不依赖源工程路径。源 H5 与原物理、配置、事件文件在导出前后 SHA 不变。

## 读取证据与耗时

- [导出完整核验](diagnostic_03_portable_audit.json)：52 个源数据集复制哈希、全部实际控制终点对齐、原标签和只读 batch。
- [独立复核](diagnostic_03_portable_independent_check.json)：所有属性、自含存储、流长度、状态/时间连续性、14 阶段、完整配置、物理记录数，以及首段、中段、尾段和尾部 padding。

正常 `MinimalPickDataset` 成功筛选构造器明确返回 `Dataset contains no complete successful episodes`。随后复用现有 `__getitem__` 和 `collate_fn` 进行诊断只读，4 个位置的动作、状态、两路图像和 padding 均与 H5 逐值相等。返回 action `[1,16,8]`、agent_pose `[1,8]`、两路 RGB 各 `[1,3,256,256]`、is_pad `[1,16]`。临时诊断索引没有改写 false 标签，读取后删除；交付 H5 中没有该索引或任何外链。

导出及导出器验证用时 **15.700 秒**，追加独立存储/属性/读取/物理计数核验用时 **2.409 秒**。这些操作未启动物理模拟、GPU、优化器、训练或推理。`read_batch.npz` 仅含一个实际读取 batch，完整轨迹在上述 H5。

八维动作不包含 effort 上限，物理重放还需完整九维命令和辅助控制；本次只读结果没有验证策略性能或物理重放。此前 `diagnostic_01` 失败 H5 和对应证据保留在独立文件夹，未被本次覆盖。
