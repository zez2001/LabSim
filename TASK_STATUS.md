# LabSim Size_v1 阶段状态

更新2026-10-21，分支codex/lab-cuvette-size-v1。原座A candidate_far_hinge完全保留；12.5mm对照、Env_v1及旧版本保留。

## 阶段A 已验证

35个独立XY尺寸假设资产，9.50–12.50mm；入口已观察最大11.00mm，11.02mm拒绝。保守全深正证书最大10.70mm，10.72–11.00mm为未认证，不宣称全局不可行。推荐10.00mm、座局部偏置[.650,.001]mm、原座底Z2mm，保守余量.350046mm。高度67.5mm、20g质量假设、拓扑/材料/碰撞参数保留，同一XY仿射派生并重新积分COM惯量。

10mm preview_01实际加载、复位和自然静置4.5s正常exit0；连续相机与当前USD269/269匹配。28/28烹饪请求有效，世界坐标双向表面样本差约14um；原座ray实测1112命中/215面，最大观察面距约44.7nm。均非全局上界，原座完整PxTriangleMesh读回/逐shape有效fallback未知。preview未开展任务且未冻结，不入失败配额，原误标签保留并在分析中排除。

新Size_v1 CPU测试及原Env_v1回归已运行，日志摘要在runtime。正式资产可通过asset_id替换；采集/训练/自动验证强制standard，不启用random。本轮取消random10验收。

## 阶段B 正在推进

重新接回完整加载：预对准、快速无接触接近、低速27mm插入、停止顶压、逐步卸载、慢松爪、撤离、3秒稳定。保留稳定200um/1deg/3s与50um穿透门槛；对准误差预算由10mm真实余量声明，不照搬12.5mm紧配预算。尚未取得本轮完整成功，不提前计5次验证。

## 阶段C 尚未执行

完整任务通过后冻结场景及依赖SHA，5次standard逐次验证，再累计20成功+20有效失败。自然失败与确定性动作偏差分组，场景不随机。正式数据资格由冻结及正常读取审计决定。当前合格配额0/0。

[阶段A资产与几何](docs/lab_cuvette_loading/Size_v1/geometry/README.md)；[旧Env_v1状态](docs/lab_cuvette_loading/Env_v1/TASK_STATUS_before_Size_v1.md)。
