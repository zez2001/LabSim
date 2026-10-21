# 正式固定场景：首10条闭合轨迹审计

本目录由`audit_readonly.py`实际读取两个已闭合、正常退出的official进程对应的**显式10个H5文件列表**生成。未扫描episode树，未打开正在运行的controlled轨迹，也没有读取或混入10.5mm开发记录。

- 当前实际合格：**成功10、失败0**，距离20/20仍缺成功10、失败20。来源均为natural组，偏差spec为null/空；未修改原始H5标签。
- 两个仿真子进程均真实wait退出0、无中断；共启动10集、闭合10集。自然补采父CLI因`max-processes=1`且未满20成功返回2，与仿真子进程退出0是不同层级，不计为任务失败。
- ACT和DP正常读取/冻结守卫均通过，action batch为`[3,16,8]`。9集训练、1集验证，完整episode划分无交叉，两者维持同一固定场景。
- 检查索引为`collection_standard/checks/ten/dataset/episode_data.hdf5`，8610字节，使用同collection树内的相对H5外链。此步骤未创建最终默认`collection_standard/dataset/episode_data.hdf5`。
- 10条的实际初态位置、姿态和9个关节观测完全一致；来源A1、目标A座、10mm假设资产、机器人/控制/物理、相机和冻结场景指纹均一致。seed0–4在两个进程重复作为编号，不是场景随机化。
- 最终深度均约27.000035mm；独立释放、撤离后3秒稳定通过，3秒位置漂移均约0.238884μm。记录的原生速度差异与静态目标完整烹饪重叠不可全读告警继续保留，不声称真实标定或广泛场景的成功概率。

`collection10_audit.json`包含严格配额准入、逐episode原SHA/标签、两个真实进程证明和正常读取结果；`normal_ACT_DP_read.json`单列读取证据；`initial_state_and_results.json/.csv`包含逐次实际初态、深度、姿态、支撑、漂移及告警。

没有重复导出大便携数据，先前正式第0集的约1.96GB独立便携成功样例仍有效。本步骤只做CPU只读分析并新建检查索引/小证据，未启动GPU、修改核心/配置/冻结或生成DOCX/最终阅读包。
