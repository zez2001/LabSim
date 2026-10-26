# 已闭合教师 v6 / v7 支撑对照图

![同一原门槛下的实际 XY、倾角和座底支撑力](teacher_v6_v7_support_gate_comparison.png)

图中橙线是 `teacher_baseline_close_01` 的原 `TASK_INCOMPLETE`，蓝线是 `teacher_support_align_01` 的原 `SUCCESS`。三栏分别是实际 XY 欧氏误差、实际倾角、分类座底支撑力；原 100 µm、0.15°、0.1 N 门槛和质量 20 g 对应的 0.1962 N 重力参考均显式标记。虚线为各次实际 OPEN 转换；蓝色菱形是 v7 原独立 `correct_target_supported` 的精确物理样本。

两条曲线分别减去各自原 SUPPORT_TRANSFER 起点，保留各自控制边界记录时间，仅画 0–5.15 s 窗口；没有插值、重采样、时间变形或逐样本配对，也不假设同阶段持续时间相同。教师阶段只用于横轴起点，成功依据是独立事件和原门槛，不是阶段名称。菱形来自原 240 Hz 物理点，可能位于曲线的 60 Hz 控制边界之间。

v6 OPEN 在相对 3.000 s，实际 XY 187.961 µm 超过原门槛；v7 OPEN 在相对 4.400 s，实际 XY 5.581 µm、倾角 0.012933°、底部支撑 0.239238 N，原门槛同时成立。v7 在支撑过渡中仍有瞬态 XY/倾角超门槛和支撑起伏，不能描述为整个 SUPPORT 阶段始终对齐或平稳。首次独立支撑事件在相对 2.4375 s；完整成功还依赖后续开爪、实际脱离、撤离和三秒稳定检查，见[完整成功支撑与便携验收](../teacher_support_align_01_support_portability_audit/README.md)。

[输入 SHA256、脚本和图像来源清单](figure_source_manifest.json) 保留两份已 final 摘要与两份 CSV 的实际路径、字节数和 SHA256。图只分析已关闭记录，没有读取第二集运行目录，没有 GPU、API、新仿真或标签修改。这是两条确定性教师记录的局部对照，不是成功率、GPT 成功或真实精度结论。

从仓库根目录复现到新目录：

```bash
/home/wujing/Desktop/vla/labutopia-env/bin/python \
  docs/lab_cuvette_loading/Project_v1_1/diagnostics/teacher_support_v6_v7_comparison_20261027/plot_support_comparison.py \
  --repo-root /home/wujing/Desktop/vla/LabSim \
  --output-dir /tmp/labsim-support-comparison-reproduction
```

输出禁止覆盖已有图；复现需选择尚未使用的输出目录。原始 v6/v7 数据与旧图片不改。
