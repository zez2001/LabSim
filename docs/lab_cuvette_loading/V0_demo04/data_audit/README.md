# V0_demo04 数据与便携交付工具

本目录区分工具验证与本轮真实实验。`collector_interface_checks.json` 只验证纯函数及临时空元数据，不是物理轨迹；`historical_failure_tool_validation.json` 使用已完成的 V0_demo03/dev_02 真实失败检查新工具，不算 V0_demo04 的新实验。新场景实际运行以后，另存新证据，不能覆盖或改写旧实验。

## 本轮已完成的有界预插入诊断

`diagnostic_03/run/trial_00` 的 10 项独立诊断检查全部通过，`diagnostic_subtask_completed=true`：76.9166667 秒、4615 个转换、18461 条含初态物理记录。实际阶段完成 ALIGN、GATE_RETRACT 和 DIAGNOSTIC_HOLD。终态 `GEOMETRY_BLOCKED_PREINSERT`；原座几何仍阻塞完整任务，workflow/native/data eligibility/real calibration 标签全部为 false。

阅读包应携带的完整自含 H5 为 `outputs/lab_cuvette_loading/V0_demo04/portable_01/episode_data.hdf5`，885,164,015 字节，SHA256 `65c32000917083544db3f881054dbf4706a606fcc368002332caf7ccf564e6b0`。全部 52 个源数据集及原属性已核验；无外链、软链、VDS 或外部存储。现有读取方法诊断只读通过首、中、尾和 padding 核对，正常成功筛选器保留拒绝结果。

阅读 [本次有界诊断先读说明](READ_FIRST_actual_diagnostic_03_zh.md)、[导出完整核验](diagnostic_03_portable_audit.json) 及 [独立复核](diagnostic_03_portable_independent_check.json)。导出核验 15.700 秒，追加独立核验 2.409 秒；未执行模拟、GPU、训练或推理。

## 本轮真实失败诊断数据

`diagnostic_01/run/trial_00` 已闭合：29.5 秒、1770 个转换，终态 `GRASP_SLIP_DURING_TRANSPORT`，实际阶段止于 TRANSPORT。全部成功、学习资格、原配套、几何及真实校准标签保持 false；这是 V0_demo04 新运行的真实失败诊断。

完整自含数据位于 `outputs/lab_cuvette_loading/V0_demo04/portable_failure_01/episode_data.hdf5`，314,819,825 字节。全部 52 个源数据集逐值哈希核对，外链、软链、VDS 和外部数据存储均不存在。正常成功筛选器拒绝此失败，随后使用现有读取方法做诊断只读；首、中、尾及 padding 的动作、图像和状态均与源数据相等。

阅读 [本次失败先读说明](READ_FIRST_actual_failure_01_zh.md)、[导出完整核验](diagnostic_01_portable_audit.json) 及 [独立复核](diagnostic_01_portable_independent_check.json)。后续运行使用独立目录及证据，不覆盖本次失败。

## 旧阅读包视频核对

`demo03_package_media_audit.json` 对桌面原 V0_demo03 阅读包只读检查：报告链接的六个 MP4 全部存在，均能 ffprobe 识别并完整 CPU 解码，未发现视频漏打或编码损坏。DOCX 中是指向相邻 `media/` 目录的外部相对链接，没有内嵌视频。单独复制/预览 DOCX 不会携带外部视频；应传整个阅读包并从本地文件打开对应 MP4。具体阅读器的点击失败原因仍未知，文件检查不能确认其安全策略或链接解析行为。原阅读包未修改。

## 新采集器

`demos.lab_cuvette_demo04.collector.Demo04Collector` 保持原 begin/cache/finish 调用接口，使用独立 V0_demo04/native_nominal 元数据及判分关口。`next_state.control_aux` 包含：

- `command_q`：实际下发的完整九维位置命令，七臂 rad 加左右指 m。
- `gripper_effort_limit_N`：本控制周期两指各自的 effort 上限。
- `gripper_target_m`：限速/限幅前的原始对称指位目标。

三者和 `available` 按控制转换末态写入 H5 `control_auxiliary/`，与 `next_timestamp` 同步。未知值写 NaN/false，不填零。H5 保存完整配置的 canonical JSON/SHA 及执行器源码 SHA，说明阶段 effort 调度来源。

`agent_pose` 第八维是左指实测位置，`actions` 第八维是左指命令；当前执行器左右命令对称，完整九维另存。八维位置目标不包含 effort 上限，不能把只读 batch 当作完整八维物理回放或策略性能验证。

正常学习成功资格要求独立 score 的工作流、几何、数据资格、单仪器及资产/槽/座绑定、所有实际阶段、末态时间与原记录哈希通过。`native_pair_success` 还须独立原配套成功且完整流程/几何均通过；本轮不会宣称真实校准。失败或缺少判分时可以闭合真实诊断轨迹，`success=false` 不因可读而改变。

## 完整自含 H5 导出

完成并关闭 episode 后，在工程根目录运行：

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo04.portable_episode \
  --episode PATH_TO_COMPLETED_EPISODE \
  --output NEW_PORTABLE_DIRECTORY
```

工具保存 `episode_data.hdf5`：复制全部实际 RGB、观测、动作、后继状态、诊断、阶段和嵌入判分，保留原标签；按物理记录精确匹配每个控制终点，验证或补入实测辅助控制及调度配置 SHA。所有源数据集的形状、类型与**完整逻辑数据值哈希**逐项比较，目标 H5 不允许外链或软链。原始绝对路径仅作为可追溯字符串，不是读取数据的依赖。

`portable_audit.json` 保存全部复制/对齐核验与源 H5 前后 SHA；`read_batch.npz` 是一个实际读取的样本，不是完整 episode。输出目录须为新目录，原始 H5 和历史输出不修改。

现有 `MinimalPickDataset` 构造器只接受 complete/success=true。真实失败保持 false，正常构造器会明确拒绝。工具随后创建仅诊断范围的临时索引，**标签仍为原 false**，复用现有 `MinimalPickDataset.__getitem__` 和 `collate_fn` 读取接口；临时索引随即删除，不进入学习成功索引。报告把这一读取写为 `diagnostic_read_only_existing_getitem_and_collate`，不会伪称正常成功过滤器已经接受失败，也不写任何假成功标签。无训练或推理。
