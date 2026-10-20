# Env_v1 物理与接触记录契约

`demos/lab_cuvette_env_v1/physics_capture.py` 的 `PhysicsRecorder` 从当前场景 `/World/Cuvette/Visual/*` 读取实际派生网格及完整相对变换；不重新加载旧14.85mm器皿，也不依赖显示数字推断几何。初始第0行保存，第一行位姿差分速度保持 unknown；之后每一个物理步结束、尚未推进下一步时同步读取刚体位姿、COM、原生速度、USD属性、关节与接触。

物理记录流式写入 `physics_records.jsonl`，原始回调流式写入 `native_contact_events.jsonl`。内存仅保留紧凑判分摘要和短窗口，不缓存图像。相机另由环境及采集器保存。

每次接触张量API明确传入 `physics_dt=1/physics_hz`，返回值按N保存；原始PhysX回调保留Ns冲量和除以当前dt后的原始力向量。回调方向仍按原API collider约定保存，不擅自标为器皿所受力。重复同一步、同一对、同一点/冲量的事件仅标记，不重复加入张量合力。

## 底部与壁体分离

当前A/B原座仍是整块Mesh碰撞输入。采集器对选定座的每个接触点单独处理：

1. 同一物理步读取 `get_contact_force_matrix(dt)` 与 `get_contact_force_data(dt)`。
2. 按每个过滤器，将原始标量力×法线求和，分别与正负方向的aggregate比较，保存所选sign、双向残差和是否可解。允许误差为max(1µN,aggregate的0.5%)；不匹配保持unknown。
3. 将点和解出的器皿所受力变换到座坐标。只有点在声明底面±50µm内、向上法向分力方向余弦≥0.5时才计为底部支撑。
4. 入口/顶部特征与孔壁接触分别标记。整座合力Z仍单独保留，但不会作为底部支撑证明。摩擦力另存，壁面摩擦承重不会误记为触底。

这只是对求解器接触点的区域归类，不是材料穿透证明。曲面、未知支撑结构或不能可靠解出的接触不能自动归为底部。`native_target_overlap_m` 和真实合法孔腔包含关系继续为 null。12.6mm方孔包络仅作为必要参考，不能遮盖原始入口凸起。

## 速度约定

- 原生：`SingleRigidPrim.get_linear_velocity()`、`get_angular_velocity()`；世界轴m/s、rad/s。保留后端刚体速度，COM参考点尚需实际差分对照，不根据方法名宣称已解释全部后端行为。
- USD：`UsdPhysics.RigidBodyAPI` 的 velocity及angularVelocity；世界轴、线速度按本场景米单位，角速度deg/s。Fabric下可能与物理张量不同步，原值保留。
- 差分：由实际世界COM位置差/当前物理dt得到线速度；由世界旋转增量log得到rad/s角速度。

四项CPU签名/接触分区测试通过；它们不是实际PhysX接触验证。实际API、方向残差、桌面自然支撑及夹持接触必须在新场景运行后核查。
