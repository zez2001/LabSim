# Size_v1 正式固定5次：实际结果与首批数据

本目录仅记录已经闭合的正式verify5，不是20成功+20失败已完成的声明。实际进程由采集driver等待结束，退出码0、无中断；5条完整任务均由独立判分及collector准入确认成功，初批合格计数为**成功5、失败0**，距离20/20仍缺**成功15、失败20**。

- `first5_collection_audit.json`：正式冻结场景及真实进程exit0双门控，全部5条通过；ACT、DP正常批次均为action `[3,16,8]`。训练4集、验证1集，按完整episode拆分，没有帧跨集合。
- `standard5_initial_state_and_results.json/.csv`：逐集实际初态、来源槽A1、目标A座、资产cuvette_xy_1000、控制/相机/场景指纹、终态深度、撤离后3秒窗口、原生物理告警和实际退出证据。5集保存的初态位置、姿态和9关节观测完全相同；记录seed为0–4，只是standard重复编号，不启用场景随机化。
- 检查索引为`outputs/lab_cuvette_loading/Size_v1/collection_standard/checks/first5/dataset/episode_data.hdf5`，仅6144字节，使用同collection树内的相对H5链接。最终默认`collection_standard/dataset/episode_data.hdf5`尚未在此步骤创建，避免后续采集后重名覆盖。
- 5集最终实际深度均约27.000035mm，撤离后3秒位置漂移均约0.238884μm，姿态变化约0.0007132°；实际张爪脱指、撤离、支撑和稳定判据均通过。这是当前确定初态/合成资产/当前物理配置下的重复结果，不是广泛场景成功概率，也不代表真实标定或平台亚微米精度。
- 原生速度与位姿差分不一致、静态目标完整烹饪重叠不可全读的告警仍保留，没有提高穿透或稳定阈值令记录通过。

`portable_episode_validation.json`为现有导出器实际执行的完整manifest副本，原始便携目录位于桌面`LabSim_Size_v1_便携成功数据样例_20261021`。26个复制文件、1,961,427,140字节；加manifest自身后实际目录27个文件、1,961,439,602字节；原始HDF5字节保留、无H5外部依赖，正常ACT/DP读取通过。两个`.jsonl.gz`由现有导出器正常复制，没有重复补写或变更manifest。

`portable_episode_archive_validation.json`另外记录流式解压SHA和字节数对照归档前原始日志，未解压落盘；旧绝对路径字符串仅为追溯元数据。便携数据读取不依赖原机器的外链H5、外部图像或原始JSONL路径。完整数据约1.96GB，单独传输，不放进小阅读包。

本步骤为CPU只读分析和导出，没有启动仿真、模型训练、修改源标签或生成DOCX/最终阅读包。
