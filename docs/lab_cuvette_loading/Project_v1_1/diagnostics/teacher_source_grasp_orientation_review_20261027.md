# 来源架约束下的 teacher 初始抓持纠姿诊断

本次只读分析已关闭的 `teacher_camera_v2_02`，并在 Project_v1_1 teacher 新实现中完成单因素控制修复。旧 controller、配置、物理、评分、原始轨迹和失败标签均不改变。原运行提交为 `4d19b6ca836ca01c998abf4c4225946e09ffc80a`；记录的最终结果仍是 `GRASP_SLIP`，虽然其后确实完成插入、脱指、撤离和稳定观察。

## 已核实的时序

父实现 `controllers/lab_cuvette_env_v1_controller.py:87-97` 依据物体相对手爪的真值姿态调整 EE 朝向，每 tick 最多 0.1°。APPROACH_SOURCE 和尚未锁存的 GRASP 均不调用该纠姿；GRASP 一旦锁存，`243-248` 每 tick 开始调用 `_feedback(debug)`，默认为 `orientation=True`。与此不同，EXTRACT 在当前配置明确设为 `extract_orientation_feedback: false`。

实际 control trace 表明：

- 首次双指接触在 18.05 s；teacher 锁存在 18.166667 s。锁存前名义 EE 姿态命令相对初始化的变化为零。
- 18.183333 s 第一次 GRASP 纠姿下发约 0.1° 改变量；随后数个 tick 的主要 Y 方向改变量反向。锁存后 GRASP 的姿态命令最大偏离初始值 0.299085°，同时名义 EE 的 XYZ 完全固定。
- 相对于 teacher 锁存参考的杯底漂移在 18.183333 s 仍仅 0.263 µm，18.20 s 已到 270.366 µm，18.25 s 到 551.722 µm。这些是 60 Hz 控制边界值，不能冒充物理子步峰值。

独立 raw 审计的参考点比 teacher 锁存稍早，在 18.145833 s；其 240 Hz 物理记录完整复算见同目录 `teacher_camera_v2_02_grasp_slip_analysis/summary.json`：杯底位置 608.994 µm、相对朝向 0.705896° 的峰同在 18.245833 s，首次越过 200 µm 在 18.191667 s。该峰时 53 mm 配置抓持锚点的位移约 64.096 µm；杆臂转动项约 652.903 µm，与杯底位移方向基本相反。因此 **608.994 µm 不能描述成纯轴向滑落**，其中包括实际杯体摇摆和手爪坐标相对转动的杠杆效应。原评分使用杯底原点，仍按原 200 µm 门槛保留失败，不用锚点较小来替换判据。

## 原因判断与限度

源码和信号先后支持的主要候选触发是：双指已经夹持、器皿仍被来源架约束时，teacher 在固定 TCP 位置下主动转动手爪，造成短时相对运动。EXTRACT/TRANSPORT 后续独立分段漂移只有数 µm，问题集中在最初静态抓持窗口。上述时序尚不等同于单因素物理因果证明，修复后必须以同配置运行核验。

空手初始朝向约偏离垂直 0.055°，锁存前器皿已经约 0.266° 倾斜，不能把全部现象只归结于空手姿态。现有不使用物体纠姿的通用抓取诊断保持得较好，但其力限和闭合目标也不同，不能作为本次控制修复的严格 A/B 证据。本轮先不同时改变空手预对准、夹爪力或摩擦；若将来需要改变空手朝向，应在张爪且尚未接触时，以独立试验插值到设计抓取朝向。

## 已实施的最小修复

仅 `controllers/lab_cuvette_project_v1_1_controller.py` 的新类 override `_feedback`：**GRASP 强制 `orientation=False`**，保持当前 EE 姿态；可显式调用的 XY 反馈仍传递给原父方法。EXTRACT 沿用原配置，TRANSPORT/ALIGN 等相位在离架后继续使用已有纠姿。四个运动相位的 1.5 倍缓速、物理 watchdog、接触计时、锁存、0.75 s 抓持等待、8 N 力限及释放逻辑不变。

版本标记为 `Project_v1_1.teacher_phase_motion_clock.v2`。每个动作 metadata 增加策略说明与实际发生抑制的布尔字段；未锁存、并未调用反馈的动作不会误称已执行抑制，重复同一时刻返回缓存动作。

## 验证状态

新增 16 项 CPU 测试，连同既有 23 项 motion clock 与 8 项原 teacher 测试，实际 **47/47 通过**。测试调用真实 controller 代码，验证闭爪后输入杯姿扰动不再改变 EE 姿态、其他相位/XY 反馈不变、原父类行为保留、接触时钟/力限/等待与 GRASP→EXTRACT 转换保持、重复时刻和 reset 正确。它们是控制软件测试，不模拟物理接触。

本次未启动 GPU/API，未触碰正在其他独立 checkout 运行的 GPT 进程。**修复后的物理有效性尚待新的关闭运行证明，不能把旧运行改写成成功。** 同名 JSON 保存控制边界样本、来源 SHA256、修复版本及测试数量。

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_lab_cuvette_env_v1_teacher.py \
  tests/test_lab_cuvette_project_v1_1_teacher_clock.py \
  tests/test_lab_cuvette_project_v1_1_teacher_grasp_orientation.py
```
