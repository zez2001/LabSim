# final_fixed_prefix_02：完整原动作前缀回归

本次进程真实 exit0，supervisor 记录 Popen.wait 返回；审计时 PID 11479 已不存在。两条原动作前缀完整执行 4 / 3 个动作，7 个目标全部到达。未调用模型，不是 GPT 演示或完整装载成功。

第三动作仍分别为 world [0,40,0] mm 和 [0,35,-19] mm，各2秒。相对每次实际起点的原目标计算：

- 序列1：旧执行器净位移 213.732 mm、终点误差 196.807 mm；首次修复误差 228.55 µm（历史进程 exit139）；本次净位移 40.000868 mm、终点误差 1.527 µm，最大瞬态跟踪误差 0.36738 mm。
- 序列2：旧执行器净位移 230.539 mm、终点误差 224.840 mm；首次修复误差 64.92 µm（历史进程 exit139）；本次净位移 39.823226 mm、终点误差 2.402 µm，最大瞬态跟踪误差 0.25084 mm。

原请求参数逐项一致；原序列2的第三动作在1.9秒终止，本次执行完整2秒。相同请求参数不代表此前跟踪后的实际起点相同。

与首次修复相比，physics/vessel/rack/scene/adapter 配置及资产哈希一致；控制、工具封装和退出流程已有变化，不能把全部差异单独归因于补偿。终点改善不代表全程精度，也不等于原座装载或真实标定成功。

旧 fixed_replay_01 的 exit139、旧 legacy_replay_03 的执行器失败以及全部原始标签、资产和记录原样保留。未读取或修改 H5。

`audit.json`：闭合证据、配置/资产保护、源SHA及解释边界；`action_comparison.csv`：全部7动作的三版本对照；`comparison.png`：终点改善与剩余瞬态误差。

物理复现使用新目录且与其他仿真顺序运行：

```bash
"$LABSIM_PYTHON" -m demos.lab_cuvette_project_v1_1.run --backend diagnostic \
  --probe fixed-replay --attempts 1 2 --headless \
  --output outputs/lab_cuvette_loading/Project_v1_1/fixed_prefix_new
```

旧分析参见 `../legacy_reproduction.md`、`../fixed_reproduction/README.md`。本目录为新增闭合对照，不覆盖它们。
