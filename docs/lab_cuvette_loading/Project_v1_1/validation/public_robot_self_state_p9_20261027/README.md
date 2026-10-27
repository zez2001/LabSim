# P9 CPU/离线就绪证据

本目录不含新的真实 GPT 请求、GPU 运行或任务结果。候选说明在 [P9 文档](../../public_robot_self_state_p9.md)。截至本验证，原共享预算未因本实现发生变化。

- [完整 CI 命令/源码前后 SHA](contracts_command.json)：760 passed、13 skipped、0 failed；[原 XML](contracts.xml) 和 [stdout](contracts_stdout.txt) 保留。
- [真实无 Git 导出](git_free_receipt.json)：82 passed，PATH 中 git 拒绝替身没有被调用；不需要 runtime LFS/URDF/USD。最初导出漏复制一个旧 P7 分析脚本，导致该旧脚本的四个导入测试失败；仅补齐导出文件后通过，未修改原 P7 测试。该探索日志以 `exploratory_incomplete_export_*` 保留，不当作源码失败或最终通过证据。
- [变化保护清单](change_audit.json)：17 份旧文件与基准 `42264193…` 原字节一致，包含 P7/P8、shared provider、物理配置、teacher、scorer；旧 tools 只有显式 P9 路由变化，实现 SHA 如实更新。
- [闭合 06/07 的反事实输入上界](closed_06_07_bounds/summary.json)：17+46 份输入最大 71,826，距 80k 最小 8,174。14 份可重建公开输入逐个复算；49 份私有历史不恢复，使用原真实 reservation 加精确新增字节差。不是实际 P9 请求或未来会话保证。
- [单集 dry-run](cli_dry_run.json)：160 max-calls、旧账本；`files_created=false`、`simulation_started=false`。

新测试包括独立 modified-DH 对照、非交换世界旋转/WXYZ、手掌与 TCP 非同向、关节/四元数无效值、锁定来源再生成、无 URDF runtime、毒化物体/teacher 字段不读、private live 项不移除而磁盘 redaction、重复观测/跨 episode、精确 JPEG/历史不变、真实 fake transport 单次委托、预算前置拒绝及旧入口字节行为兼容。

本体盒是 authored INPUT 的局部 AABB，不是 PhysX 实际烹饪形状或安全净空。hand 盒不包括指端和持物。独立 [frame 兼容证据](../public_robot_self_geometry_p9_frames_20261027/compatibility.json) 仅说明锁定名义 URDF/机器人输入模型的坐标关系相符，不证明真实精度。
