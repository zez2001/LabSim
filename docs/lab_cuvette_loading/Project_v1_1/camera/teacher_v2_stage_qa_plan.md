# 腕相机 v2：单次 teacher 全流程图像 QA 与小规模 API 比较

本页记录已实现的独立 QA helper 与待执行验证步骤。**本文编写时没有修改相机配置，没有运行新 teacher、GPU 或 API；不能据此宣称 v2 全流程可见或已发送模型。** 原挂点的 CPU v2 投影分析见 `mount_v2_cpu_projection.md/json/png`，CPU 投影不是新渲染证据。

## 当前源码与证据边界

- 原生公开图像来自 `tasks/lab_cuvette_loading_env_v1.py::_public_observation()` 的 `self.images`，`ProjectEnvironment.observe()` 加入公开相机标定。当前标准配置原生尺寸为 640×480。
- 正常采集器使用 `_collector_state()` → `policy_image()`，将原生 RGB 拉伸为 256×256 CHW 保存到 H5。该图像可验证数据读取，但不能重建原生 640×480，也不能恢复真实的 512×384 provider 输入。
- `side_camera.mp4/wrist_camera.mp4` 是原生视图的有损录像。适合人工回看；视频截帧不能冒充 exact wire JPEG。
- 真正 GPT 循环 `policy/backends/cubence_tools.py::run_episode()` 每次先调用 `observation_content()`，再由 `save_observation_artifacts()` 保存已编码的两张 JPEG 和第一个公开 JSON 文本，然后将同一份 `contents` 传给 provider。`gpt_control/policy_trace.jsonl`、request label 和 SHA256 绑定实际请求。即使请求失败，也保留发送前的输入；是否发起网络请求仍需结合共享 ledger 确认。
- 既有 `ManualProbe.snapshot()` 只在确定性诊断中保存 512/q60/low 编码预览至 `model_input_preview`。它没有调用 API，所以不能把其图片称为模型实际收到的图像。
- 旧 `scripts/probe_cubence.py --image...` 的图像 `detail` 硬编码 `low`。`--image-max-side 640` 并不会切换为 high。该脚本记录来源和编码哈希，但不保存 exact JPEG 文件，不能代替本页的完整比较证据。

## 独立 helper 与集成点

新增模块：`demos/lab_cuvette_project_v1_1/camera_audit.py`。其 `TeacherCameraAudit` 不导入 Isaac，不读取 debug/物体真值，不调用执行器或网络。每次快照只调用一次公开 `facade.observe()`，并从同一帧保存：

1. `native_rgb/side_camera.png` 与 `wrist_camera.png`：未裁剪、无叠加、无损原生 RGB，并记录文件 SHA256 与原始 RGB 字节 SHA256。
2. `512low/observations/decision_XXXXXX/`：512 最大边、JPEG q60、detail=low，原生 4:3 帧得到 512×384。
3. `640high/observations/decision_XXXXXX/`：640 最大边、JPEG q60、detail=high，原生帧保持 640×480。
4. 每套预览都有原 provider encoder 保存的 exact JPEG、公有 JSON、逐图 resize/K 映射与 SHA256。没有 GT crop，也不会在原图上绘制框、坐标、阶段文字或高亮。
5. 阶段名称仅写入 `stage.json`/`audit.json` reviewer sidecar。公开 JSON 和 API payload 中没有 teacher phase、评分器、debug 或器皿真值。全部 teacher 快照标为 `evidence_kind=teacher_encoded_preview, api_sent=false`。

建议由 launcher 在新版本 teacher 分支接入以下最小 hook，**本页尚未改动 launcher**：

```python
from demos.lab_cuvette_project_v1_1.camera_audit import TeacherCameraAudit

# 当前 episode reset 完成、首次公开图像已产生后创建；每集创建新对象。
camera_qa = TeacherCameraAudit(env.episode_dir / "teacher_camera_audit")
camera_qa.capture_if_phase_changed(facade, "RESET")

# 在现有 teacher 循环中，保留原来 teacher.act / env.step / 判分逻辑。
env.step(action)
camera_qa.capture_if_phase_changed(facade, teacher.phase)

# 循环结束后，无论成功还是失败，额外保存最后实际可见状态。
camera_qa.capture(facade, teacher.phase, event="terminal")
```

快照本身不推进物理，不改变 teacher 动作。边界快照是执行该新阶段第一控制步后的实际帧，应按记录的 observation ID、仿真时刻和相机 sensor 时间解释，不能把阶段标签当作动作完成或支撑已成立的证明。终止时刻以实际评分及事件为准。

## 一次连续运行的关键帧选择

固定新挂点后，运行一次完整 teacher，保存整个原生双相机视频、H5、动作与物理记录，再从上述边界快照核对：

- 初始：`RESET`；来源架、目标器皿、单台仪器与开盖关系。
- 接近：`APPROACH_SOURCE` 起点，以及进入 `GRASP` 时的近物接近终点。
- 闭爪：进入 `EXTRACT` 的帧；结合双指接触及实际夹指开口核对，不用 `GRASP` 标签证明已闭合。
- 抬升：进入 `TRANSPORT`；核查器皿和架边/相邻器皿净空。
- 搬运：`TRANSPORT_HOLD` 若实际出现，以及 `ALIGN` 边界；两相机的 held cuvette 和仪器腔口可见性。
- 预插入：`INSERT` 边界；查看杯底、原座入口、夹指和盖板，不只看 TCP。
- 支撑：`SUPPORT_TRANSFER`；可见底部关系与记录支撑/卸载信号联合判断，不能由图像单独确认承托力。
- 开爪：`OPEN` 起点和 `RETREAT` 边界；确认双指实际张开与物体分离。
- 退让：`VERIFY` 边界及 terminal；连续录像、实际撤离距离和随后至少 3 秒稳定结果共同核验。

如果运行中止，未到达的阶段明确为 unavailable；保留最后真实 terminal 快照，不补造后续阶段。即使 teacher 成功，也只证明该控制器轨迹下的渲染和可见性，不能自动外推 GPT 的所有可能姿态。

对每个阶段，人工记录 side/wrist 各自是否看得见器皿、双指、架口、腔口与目标座，遮挡来自手体/手指/盖板/机壳还是视野之外。目标像素高度只作离线 QA；不将物体真值框、中心点或裁剪图送给策略。

## v2 配置和一次物理运行

原标准配置当前仍是 wrist `localeye_m=[0.075,0,0]`、`localtarget_m=[0,0,0.10]`。CPU 候选为下面两项，其余 parent、lens、up、分辨率不变：

```yaml
cameras:
  wrist_camera:
    localeye_m: [0.075, 0.0, 0.04]
    localtarget_m: [0.0, 0.0, 0.12]
```

这不是“相机完全位于手体之前”的几何保证。已有 CPU 光线抽样只预测手体遮挡可能减少；真实手指、器皿、盖板和全过程遮挡仍待实际渲染。

只有在 root 完成独立 v2 配置/契约和上述 hook 后，才运行对应新配置。直接 launcher 支持 `--config`，避免误用未改的默认配置：

```bash
cd /home/wujing/Desktop/vla/LabSim
/home/wujing/Desktop/vla/labutopia-env/bin/python \
  -m demos.lab_cuvette_project_v1_1.run \
  --config /absolute/path/to/reviewed_v2_config.yaml \
  --backend teacher --episodes 1 --seed 0 --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/teacher_camera_v2_01
```

这里的 v2 配置路径是显式待替换项，不表示该文件或新运行已经存在。输出目录必须未存在，共用 GPU 顺序运行。不要在 fine01/fine02 跟踪对照之间切相机。

## 512low / 640high 的两次实际 API 比较

模块提供可选 `compare_preview_requests()` 和 CLI，从一个已关闭 episode 的 `stage_XXXXXX` 目录读取两套已保存 JPEG，校验 SHA256，直接构造 data URL，**不会再次编码**。每个条件发送同一时刻的两张相机图片、公有机器人状态和标定。没有工具、没有运动、没有仿真环境；每个条件最多一个网络尝试，禁用重试、响应最多 256 token、每条件 deadline 最多 60 秒。

以下命令仅供 root 在明确选择真实阶段后执行，本文没有执行。必须沿用已经累计的共享 ledger，不创建新预算：

```bash
cd /home/wujing/Desktop/vla/LabSim
CUDA_VISIBLE_DEVICES='' OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  /home/wujing/Desktop/vla/labutopia-env/bin/python \
  -m demos.lab_cuvette_project_v1_1.camera_audit \
  --snapshot /absolute/path/to/closed/episode_0000/teacher_camera_audit/stage_XXXXXX \
  --provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6.json \
  --budget-ledger /home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/camera_comparison_512low_640high_01 \
  --allow-network
```

凭据只通过既有私有环境中的 `CUBENCE_API_KEY` 读取，不写入命令、配置、日志或文档。CLI 需要预算文件已经存在，否则拒绝。旧累计预算 $30/1500 次仍由同一个 `BudgetLedger` 执行；所有 timeout/服务错误照常占用尝试并保留未知 usage reservation。不要用本示例开启新的空 ledger。

比较输出独立于 teacher 预览，含发送前再次保存的 exact 输入、原始预览来源哈希、request label、网络尝试数、返回模型、usage、简短可见回答及共享预算前后值。不会保存 HTTP header、Token 或隐藏 reasoning。源 teacher `api_sent=false` 标记不改写；只有新比较记录按实际账本尝试数另标 `api_sent`。

**判读限制：** 512low 与 640high 同时改变像素边长和 provider detail，是两个端到端传输条件，不能由一次两条件结果归因到某个单因素。两条件都用 q60、同一原生帧和同一提示。先比较真实可见性、模型是否诚实报告遮挡、输出/usage/耗时及模型身份完整性；不以回答长度作为视觉准确率。HTTP 200 但缺少 model 字段仍是 `RETURNED_MODEL_MISSING`，不能当成功，也不能推断服务实际上替换了模型。现有 640 超时或身份缺失的历史证据保留，不宣称原因已确定。

## CPU 验证与本轮未执行项

已实际运行的 CPU 验证：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 CUDA_VISIBLE_DEVICES='' \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -m pytest -q \
  tests/test_lab_cuvette_project_v1_1_camera_audit.py \
  tests/test_cubence_backend.py tests/test_cubence_project_v1_1_tools.py
```

结果：新增 6 项 + 既有 46 项，共 **52 passed**。测试核对单次 observe、原生 PNG 像素、512/640 分辨率、JPEG 原始 bytes 与 SHA、相应 K、phase/GT 排除、重复阶段去重、防覆盖、篡改检测、无工具/无重试及错误保留。API 使用 CPU fake client，没有真实网络、GPU、物理运行或成功标签生成。

待实际执行：v2 配置应用、teacher 全流程、真实各阶段快照人工检查、选定阶段 512low/640high 两次真实请求、随后按需独立 GPT 评测。没有运行的项目仍标待执行。

后续集成记录：`run.py` 已接入 phase hook，标准配置已设为上述 v2 固定挂点并记录 `project.camera_version=Project_v1_1.wrist.v2`。这只是源码接入，实际渲染/teacher/GPT 结果仍须由新运行验证；前述 helper 编写时状态作为历史边界保留。
