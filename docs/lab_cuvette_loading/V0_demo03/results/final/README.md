# 本轮完整结果证据

results.csv 汇总18条完整结束的物理运行和1条工具143中断未评分的尝试，开发、固定、随机与中断分开。正式随机10条由原目录seed8000–8007与恢复目录seed8008/8009构成。原seed8008停在INSERT，原因未知、无末态评分、不视为物理失败，也不计入成功索引。原始不完整H5和录像原地保留，不修复或补写。episodes目录保留配置、初态视图、控制器结果、独立判分、最终采集资格、运行参数及来源哈希。initial_view将未测量的NaN明确转为null，原始文件不改。

完整physics_records、native contact、H5和场景USD仍在各自outputs原目录；本阅读包不包含这些原始大文件。两个raw/最终资格记录层的语义见 ../../data_audit/formal_batch_audit_tool.md。

固定批次任务5条均完成，末尾批处理外壳返回143，原因未确证，原空summary保留；新summary_recovered_01独立重算通过。随机批次按相同seed/config逐条顺序启动，driver_outcomes保存观察到的进程退出码。run_wall_timer_s不包含SimulationApp冷启动及其后大型JSON写出/关机，不能用于端到端性能认证。
