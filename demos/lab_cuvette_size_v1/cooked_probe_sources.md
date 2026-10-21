# Isaac Sim 5.1 本机碰撞读回接口核查

本轮只读核查安装源码，没有启动额外 Isaac 进程，也没有升级或安装软件。
安装目录：`/home/wujing/Desktop/vla/labutopia-env/lib/python3.11/site-packages/isaacsim/extscache/`。

- `omni.physx-107.3.26+107.3.3.lx64.r.cp311.u353/omni/physx/bindings/_physx.pyi:2047`：`PhysXCooking.request_convex_collision_representation`。当前绑定不提供旧版的 `get_nb_convex_mesh_data` / `get_convex_mesh_data`。
- 同文件 `:3142`：返回 `PhysxConvexMeshData.vertices / indices / polygons`；每个 polygon 有 `index_base / num_vertices / plane`。
- `omni.physx.demos-107.3.26+107.3.3.cp311.u353/omni/physxdemos/scenes/ConvexMeshDataDemo.py:151`：官方同步请求示例，`run_asynchronously=False`，`on_result` 接收状态与凸体列表。
- `omni.physx.tests-107.3.26+107.3.3.cp311.u353/omni/physxtests/tests/PhysxCookingInterface.py:58`：官方 Python 绑定测试，使用 `UsdUtils.StageCache.Get().GetId(stage).ToLongInt()` 与 `PhysicsSchemaTools.sdfPathToInt(path)`，检查 `RESULT_VALID` 及返回面结构。
- `_physx.pyi:2194`：`PhysXSceneQuery.raycast_all` 查询实际已附着物理场景。
- `_physx.pyi:3604` 和 `:3651`：callback 对象使用 `face_index` / `rigid_body`，并非 closest-hit 返回字典中的 `faceIndex` / `rigidBody`。探针统一输出后者名称。
- `_physx.pyi:2493`：`get_physxunittests_interface().get_physics_stats()` 返回整场景实际 shape 类型计数；不能从全局计数独立断言某一个座的类型。
- `omni.physx.asset_validator-107.3.26+107.3.3.lx64.r.cp311.u353/omni/physxassetvalidator/scripts/cookingApproximationChecker.py:123` 起的 `CookingApproximationFallbackChecker`：动态刚体中原始 triangle mesh 不受支持的规则。此检查器本身检查 USD 配置，不提供 attached shape 完整网格读回。

`cooked_probe.probe()` 在已 reset 的同一场景内同步请求比色皿每个凸体的烹饪表示，然后对原座进行六方向真实物理 raycast 表面抽样。当前修正版在输入/返回两侧都应用完整 local-to-world 矩阵及场景单位，记录全部顶点和三角面中心到另一侧三角表面的双向距离；不是最近顶点距离，也不是复合并集外表面的严格误差上界。

`preview_01` 原始 JSON 的单向顶点距离全部为0，但不能据此推断面片完全一致。只读补充分析观察到面中心样本约13.6–14.0μm差异，见 `docs/lab_cuvette_loading/Size_v1/physics/cooked_preview01_summary.{json,md}`。原始 preview 度量只乘 stage metersPerUnit、遗漏局部 Xform 缩放；旧文件保持不变，修正版保存正确世界米坐标度量，并将旧计算单独标记为 deprecated 来源对照。

必须保留以下限制：烹饪表示请求并不等于读取 attached PxShape 的指针；本机公开 Python 绑定未发现静态 PxTriangleMesh 完整顶点/索引的读回方法。真实 raycast 能证明观察到的面参与查询，但未被射线触及的面、内部表面及回退仍可能未知，不能将采样最大值称为全局上界。不得为了诊断更改座的 approximation、清空运行中缓存、重新 attach stage 或临时创建替代碰撞体。
