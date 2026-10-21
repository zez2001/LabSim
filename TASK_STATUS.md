# LabSim Size_v1 阶段状态

更新2026-10-21，分支codex/lab-cuvette-size-v1。原座A candidate_far_hinge完全保留；12.5mm对照、Env_v1及旧版本保留。

## 阶段A 已验证

35个独立XY尺寸假设资产，9.50–12.50mm；入口已观察最大11.00mm，11.02mm拒绝。保守全深正证书最大10.70mm，10.72–11.00mm为未认证，不宣称全局不可行。推荐10.00mm、座局部偏置[.650,.001]mm、原座底Z2mm，保守余量.350046mm。高度67.5mm、20g质量假设、拓扑/材料/碰撞参数保留，同一XY仿射派生并重新积分COM惯量。

10mm preview_01实际加载、复位和自然静置4.5s正常exit0；连续相机与当前USD269/269匹配。28/28烹饪请求有效，世界坐标双向表面样本差约14um；原座ray实测1112命中/215面，最大观察面距约44.7nm。均非全局上界，原座完整PxTriangleMesh读回/逐shape有效fallback未知。preview未开展任务且未冻结，不入失败配额，原误标签保留并在分析中排除。

新Size_v1 CPU测试及原Env_v1回归已运行，日志摘要在runtime。独立探索配置可通过asset_id替换，冻结采集配置不允许替换；采集/训练/自动验证强制standard，不启用random。本轮取消random10验收。

## 阶段B 完整成功且5次standard全部通过

重新接回完整加载：预对准、快速无接触接近、低速27mm插入、停止顶压、逐步卸载、慢松爪、撤离、3秒稳定。保留稳定200um/1deg/3s与50um穿透门槛；对准误差预算由10mm真实余量声明，不照搬12.5mm紧配预算。10.00mm loading_01已实际完成全流程，105.8167仿真秒/6348控制步/exit0，独立成功true。实际承托94.4875s、双指脱离95.1s、撤离98.6333s，最后3秒稳定；位移漂移.239um，姿态变化.000714deg。原座未改，native_pair原12.5结论不翻true。此为开发demo，未带最终冻结指纹，不计正式20条。10.5mm边界探索已完成但独立判为GRASP_SLIP，且进程实际退出143，开发记录保留不计正式配额。10mm配置已冻结75项依赖，5次standard全部完整成功，批次实际正常退出0且5集原始日志均无损归档。10.30mm开发尺寸验证也已完整成功，实际父wait exit0，105.7833仿真秒/6346控制步；原座三个USD层和world输入数组SHA与10/10.5相同。它不计冻结10mm配额。离散10.0/10.3成功不能称连续物理范围；10.5原门控失败不等于已证明几何不能插入。

## 阶段C 已有20条合格成功和1条合格受控失败

5次冻结standard验证与随后三批共15条自然补采均完整成功，四次自然仿真子进程actual exit0、无中断。20条成功及首条受控失败均通过production逐集准入、真实进程、无损归档及ACT/DP正常读取核验；成功按完整episode划分18条训练、2条验证，无训练执行，场景随机化关闭。合格成功20、失败1；尚缺19条有效失败，正在同一冻结场景中采集确定性INSERT提前停止。首条同场景INSERT提前停止已实际核验：62.383333s、实际深度1.016965mm，child exit0、record_valid=true、CONTROLLED_EARLY_STOP；没有释放/撤离，post_retreat_window unavailable且stable_after_retreat=null。实际事件、H5和配置一致，成功/失败各ACT/DP读取均通过。首集约1.96GB便携副本已实际导出并正常读取，无HDF5外链。自然失败与确定性动作偏差分组，场景不随机，不把开发尺寸探索和预检计入配额。

[阶段A资产与几何](docs/lab_cuvette_loading/Size_v1/geometry/README.md)；[旧Env_v1状态](docs/lab_cuvette_loading/Env_v1/TASK_STATUS_before_Size_v1.md)。
