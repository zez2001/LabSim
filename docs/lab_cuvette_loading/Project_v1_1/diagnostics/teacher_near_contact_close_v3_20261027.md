# Teacher v3：近接触闭爪限速

本次在 `590f346` 的 v2 基础上增加一个控制因素：接近名义器皿宽度时提前减慢闭爪。保留 v2 的 GRASP 不纠姿、原父 controller、通用夹爪 helper、力限、驱动增益、几何、物理和评分。没有更改来源架或器皿尺寸，也没有提高原 200 µm 抓持判据。

## 规则与记录

仅在动作来源相位为 GRASP、调用父 controller 前尚未锁存、当前真实手指力没有形成双侧接触、父输出仍要求关闭时检查。若上一总开口不大于 `max(vessel.outer_xy_m) + 0.002 m`，下发目标取：

```text
max(父 controller 的开口目标,
    上一次实际下发的 controller 开口目标 − gripper.contact_approach_speed_m_s / control_hz)
```

当前配置名义宽 10 mm，对应门槛 12 mm；复用原已有 2 mm/s 近接触速度，60 Hz 每 tick 最多闭合 0.033333 mm。门槛之前的父请求仍为 20 mm/s。本规则不会加速原本更慢的父请求，且不会修改真实双侧接触后的冻结和锁存动作。只见单侧接触不会设置 `_first_bilateral_seen`，也不会制造接触或成功事件。

调整后同步 `last_grip_opening` 和缓存动作，重复同一观测时刻不再多消耗一次闭爪步进。动作 metadata 记录名义宽、门槛、复用速度、上一目标、父目标、下发目标、所处限速区、是否实际限速及传感器双侧状态。宽度来自配置中的资产名义尺寸，没有使用物体真值位姿或力推断一个新尺寸。

新版本为 `Project_v1_1.teacher_phase_motion_clock.v3`，标准配置两处版本标签同步。`vessel.outer_xy_m` 必须提供两个正的有限名义尺寸；错误配置不会静默猜测宽度。

## 已验证与下一步

新增 30 项 CPU 测试，连同原父 teacher、phase clock 和 v2 GRASP 姿态测试，共 **77/77 通过**。覆盖门槛内外、零/单/双侧接触、原冻结锁存、重复观测、后续 tick 的前一目标、较慢父请求、其他相位不变、配置宽度/速度、reset 和非法配置。测试是软件时序及目标限幅检查，不模拟真实接触。

这个原子改动针对首次触碰时的冲击/摇摆候选原因。原 `teacher_camera_v2_02` 在单侧初触到锁存前已经发生器皿倾斜，v2 只取消锁存后纠姿，不能据此宣称全部来源端接触问题已解决。正在独立 checkout 执行的 v2 运行及其原始记录不受本次 root 工作树修改影响，其结果等待独立闭合审计。

**v3 没有运行新的物理实验或调用模型 API，改善是否成立、是否满足原评分仍须同一标准配置的新运行验证。** 不能把通用控制的有效抓取结果泛化为本 teacher 已通过，也不能把 teacher 的问题归结为所有共享控制均失效。

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q \
  tests/test_lab_cuvette_env_v1_teacher.py \
  tests/test_lab_cuvette_project_v1_1_teacher_clock.py \
  tests/test_lab_cuvette_project_v1_1_teacher_grasp_orientation.py \
  tests/test_lab_cuvette_project_v1_1_teacher_near_contact_close.py
```
