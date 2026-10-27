# P9：公开机器人自身运动学候选

P9 只在 P8 的相同双图、固定 detail、单张历史腕图和 context2 上，增加一个 CURRENT 机器人自身 JSON 组。原 CURRENT 状态及双图五块仍在最后，使用原身份；额外文字在原客户端计算输入上界和预算预留之前进入请求。没有额外 API、自动动作、规划器、目标座/器皿/障碍真值、环境距离或安全路线。

`policy/robot_self_kinematics.py` 是各 backend 可共同导入的纯 CPU 库。输入仅为公开实际关节的前七个值、公开 actual TCP 及其身份/时间。它依据普通 Git 中的 `config/lab_cuvette_loading/Project_v1_1/robot_self/franka_nominal_kinematics.json` 求局部 FK，并计算 `T_world_base = T_world_TCP × inverse(T_base_TCP(q))`，得到 link6、link7、panda_hand 的名义世界坐标。runtime 不读取 URDF、USD、LFS 缓存或环境。

静态模型源 URDF SHA 为 `e9024642…`。hand/TCP 来自 link8 的两条分支：link8→hand 为 Rz(−45°)，link8→TCP 为 Rz(135°)、z=0.1m，合成 hand→TCP 为 Rz(180°)、z=0.1m；不是假设二者同向。普通 Git 的 `tests/fixtures/lab_cuvette_project_v1_1/robot_self/` 保留源 XML/机器人局部盒原字节及来源 SHA，可在不下载 LFS 的导出目录复现生成。

所附三块包围盒来自锁定 Franka USD `312a326e…` 的 authored collision INPUT 顶点，按各刚体自己的局部坐标求 AABB。它们可填平自身凹部、超过真实材料；不是 PhysX cooked shape、接触偏置、扫掠体或真实标定。hand 盒明确不含手指和持物，仍需检查原双图。

[静态来源与顶点包含证明](validation/public_robot_self_geometry_p9_feasibility_20261027/README.md) 与 [坐标兼容门](validation/public_robot_self_geometry_p9_frames_20261027/compatibility.json) 是独立 CPU 证据。后者从 USD Physics joint 两端局部坐标建立关节链，在已闭合 05/06/07 的公开关节值上对照相对 TCP 的 URDF FK：最大差约 0.245µm / 6.52×10⁻⁸rad。它只核查这两份名义模型的坐标一致性，不是仿真、实物或碰撞净空的精度结论。没有输出未经核验的像素投影。

新增提示只说明：机器人自身坐标不是障碍/支撑判断；预接触时尚无支撑是正常现象，不应单凭它立即结束。在图像支持对准和下一局部净空时，仍按原低速/100µm/卡滞规则逐步寻求允许的任务接触、重新观察；实际异常、无安全依据时停止，不提前释放。没有给方向、高度、距离、waypoint、目标世界坐标或专家动作。

独立 profile 为 `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view_self_state.json`。P7/P8 模块、profile 和原数据保持原字节；共享入口只增加显式 `robot_self_state` 路由，原 profile 的实际 prompt/payload/tool/action 行为由兼容测试核查。实现文件 SHA 随路由变化而如实记录，不能说 metadata 字节完全不变。

生成命令（必须是锁定源字节，拒绝覆盖）：

```bash
python -m policy.robot_self_kinematics \
  --urdf tests/fixtures/lab_cuvette_project_v1_1/robot_self/lula_franka_gen.source.xml \
  --boxes tests/fixtures/lab_cuvette_project_v1_1/robot_self/robot_local_boxes.source.json \
  --output /tmp/franka_nominal_kinematics.NEW.json
```

仅打印计划、不启动仿真的入口：

```bash
./labsim eval --project-version Project_v1_1 --backend gpt6 --episodes 1 --max-calls 160 \
  --provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view_self_state.json \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_P9_NEW --dry-run
```

上限仍为 $30 /1500 请求、80k 输入保守上界、1024 输出、low effort、160 决策及原动作边界。闭合 06/07 历史不变的反事实检查见 [逐前缀上界](validation/public_robot_self_state_p9_20261027/closed_06_07_bounds/summary.json)：63 份输入最大 71,826，距 80k 最小 8,174；14 份完整公开输入独立复算，49 份私有历史不恢复，只保留原真实 reservation 再加精确新增字节差。未来响应与会话可能变化，原客户端仍会在网络前拒绝超限；这不是未来成功或成本保证。

截止 GPT07 的共享预算余量只有 $5.156470。仅本地 CPU/离线验证不能证明这笔余额足以完成下一集，尤其接近入口需要更多观察。P9 尚无真实 API 或仿真结果，不能列为任务成功。
