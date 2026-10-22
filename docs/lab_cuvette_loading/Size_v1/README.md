# Size_v1 固定原座的比色皿尺寸实验

当前开发与交接分支为`codex/labsim`。Size_v1原实验末端保存在`archive/20261022/lab-cuvette-size-v1`标签。原A座candidate_far_hinge、整机、来源架及其物理参数不变。尺寸是XY仿射派生假设，不是实物测量；高度67.5mm、质量假设20g不变，质心惯量按相同材料体积分模型重算，密度不假设同时保持。

[阶段A全部35个资产与几何结果](geometry/family_20261021_02/README.md)、[注册清单](../../../../assets/lab_cuvette_loading/Size_v1/registry.json)、[实际烹饪探针](physics/cooked_preview01_summary.md)。10.00mm开发演示已实际完整成功，包含松爪、撤离及3秒稳定；未冻结开发轨迹不计正式配额。10.50mm边界探索独立判分失败，不能由最终留在座内推断完整成功。

从工程根目录运行，新输出目录不可存在：

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher --headless \
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \
 --output outputs/lab_cuvette_loading/Size_v1/NEW_LOADING_RUN
```

默认GUI，省略`--headless`。正式standard配置已冻结10mm资产，其他asset_id会被冻结检查拒绝。资产替换需使用独立未冻结探索配置，不计正式配额；配置asset_id由解析器同步更新视觉、碰撞、尺寸和惯量，原座不变，其他尺寸不能继承10mm物理成功。几何重算、物理contact、输入材料几何检查和完整独立评分分开保存。

采集、训练及训练内自动验证都强制standard并禁用场景随机化；训练RNG种子另行固定。已生成冻结配置及依赖清单，正式5次standard已实际5/5完整成功、进程正常退出0，已完成20条合格完整成功及20条有效受控失败并通过最终审计和ACT/DP正常读取；失败为1/5/10/18mm提前停止各5条，不是自然卡滞，本轮不运行random。旧Env_v1与全部历史资产输出保留。

正式顺序验证（新目录不可存在）：

```bash
../labutopia-env/bin/python scripts/collect_lab_cuvette_size_v1_standard.py \
 --phase verify5 --collection outputs/lab_cuvette_loading/Size_v1/NEW_COLLECTION --headless
```

检查实际5/5通过证据后，同一目录运行`--phase success --allow-after-verified-five`，再按自然失败缺口运行`--phase controlled_failure --allow-after-verified-five`。每进程最多5集，非零退出、初始化无效和接口诊断不计配额。

[最终报告与连续录像](results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.md) · [40集实际审计](data/final40_actual/README.md)。训练未执行，两组均按完整episode划分18/2，collect/train/自动验证保持冻结standard。
