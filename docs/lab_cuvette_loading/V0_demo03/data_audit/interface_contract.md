# V0_demo03 数据与独立判分接口

本文件描述接口及接口测试，不代表物理任务已通过。实际连续轨迹、重复测试和训练 batch 验收以运行后独立结果为准。

## 明确模式

- `scene_mode=video_demo_adapted`。
- `task=lab_cuvette_loading_V0_demo03`。
- `data_scope=lab_cuvette_loading_V0_demo03_video_demo_adapted`。
- `native_pair_success=false`、`real_calibrated=false`，包括流程成功时。这两项不阻止明确标记的 adapted 模式仿真数据资格。
- 仍须通过完整来源架、指定来源槽、正确腔内派生 A 座的场景和几何验收。没有用厂家身份确认代替此模式的场景验收，也不把工程改造说成原 CAD 配套成功。

新实现仅位于 `demos/lab_cuvette_demo03/`，继承已有采集器与现有 `MinimalPickDataset`，不修改旧数据、旧判分或训练框架。

## 原始物理记录

每个物理步末记录原有时间、物体位置和 wxyz 姿态、COM、原生线/角速度、USD 原始速度、COM/姿态差分、关节、实际 TCP、目标、手指法向力、环境力、穿透及阶段。速度不相互覆盖；原生非有限值不能通过，有限但与差分不一致保留为告警。

新增 `target_support_force_vector_N`：仅目标座支撑底面施于器皿的净世界坐标力。力由冲量按当前 physics_dt 换算，只统计器皿侧，不把双边事件重复加和。支撑交接及撤离后窗口使用其竖直分量；环境总力仍保留为另一通道。

每步 `independent_geometry` 由实际源几何/接触审查计算，不能用下发 TCP 或阶段完成标志代填：

- `source_slot_id`、`target_seat_id`：与本 episode 元数据一致。
- `source_supported_inside_designated_slot`：实际在选定来源槽内受支撑。
- `source_clearance_m`：器皿最低外轮廓高于该来源槽口的实际净空。
- `depth_m`、`bottom_signed_gap_m`、`inside_checked_target_void`：实际目标局部坐标下的深度、底部间隙及完整器皿轮廓合法性。
- `robot_to_vessel_clearance_m`：整只手爪与器皿的实际几何净空，不是 TCP 高差。
- `forbidden_robot_environment_contact`：机器人与架体、盖板、腔壁等非允许接触的实际事件审核。

器皿为动态刚体；运行中绑定、瞬移、冻结、删关键碰撞不能通过 runtime integrity。50 μm 源几何穿透门槛保留。

初态用 RESET 最后三秒实际稳定、来源槽支持及接触检验，允许之前安全初始化后自然落稳。拔出看实际外轮廓越过槽口且双指持物。装载看实际深度、底部间隙和腔内合法目标。松爪看真实双指关节和实际脱离。撤离看整手净空。末态至少三秒，保留原 0.2 mm 漂移、1° 姿态变化和 50 μm 穿透门槛。

没有进入 VERIFY 或缺独立净空，`post_retreat_window=unavailable`，`stable_after_retreat=null`；中止前最后窗口只叫 `terminal_window`。只有控制器进入 VERIFY 时的记录可保留为 `controller_verify_window`，不能自动当成已完成撤离。物理记录须每个 physics_dt 连续覆盖，稀疏端点不能代替连续三秒。

## collector 与资格

`Demo03Collector` 保留双路 RGB、obs-before-action/next-after-substeps、8 维绝对关节目标和 9 维机器人位置。新增 H5 diagnostic 包含原生与差分速度及目标底面力，geometry 包含测量及逐帧槽位 ID。未知浮点写 NaN，布尔使用 -1 未知/0 假/1 真，ID 未知为空字符串；不以零填充缺测。

流程开始时 success、workflow_success、data_eligible、full_task_eligible 都为 false。结束时先保存原始 physics_records/events/result 并 flush H5，调用 `analyze(folder, contract=...)`，用新文件保存返回 score，最后调用：

```python
collector.finish_episode(result, independent_score=score_path)
```

仅同 episode、同资产/模式/槽位、末状态时间一致、物理及事件哈希一致、所有必需独立检查通过的 sidecar 能开启本次新 H5 的成功资格。控制器单独返回 WORKFLOW_SUCCESS 不足以放行。

`data_check.py` 再检验原 H5 资格、独立 score、绑定、观测/动作时间对齐、双 RGB/机器人/动作形状、逐帧槽位、原生/差分/目标底力、缺测标志；通过后用只读外链索引调用原 `MinimalPickDataset` 读取 batch。它不改原 H5 的 success，不把旧工程演示纳入新任务索引，不用空或伪造样本制造 batch。

## 调用

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.analyze EPISODE_DIRECTORY \
  --contract SCENE_CONTRACT_JSON --output NEW_SCORE_JSON
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.data_check \
  --episode EPISODE_DIRECTORY/dataset/episode_0000.h5 \
  --score NEW_SCORE_JSON --output NEW_INDEX_DIRECTORY
```

输出路径须为新的路径。完整 batch 通过只说明当前明确 scope 的仿真样本可读，不证明原 CAD 配套、真实尺寸标定或训练质量。
