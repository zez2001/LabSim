# Size_v1 固定原座的比色皿尺寸实验

开发分支`codex/lab-cuvette-size-v1`。原A座candidate_far_hinge、整机、来源架及其物理参数不变。尺寸是XY仿射派生假设，不是实物测量；高度67.5mm、质量假设20g不变，质心惯量按相同材料体积分模型重算，密度不假设同时保持。

[阶段A全部35个资产与几何结果](geometry/family_20261021_02/README.md)、[注册清单](../../../../assets/lab_cuvette_loading/Size_v1/registry.json)、[实际烹饪探针](physics/cooked_preview01_summary.md)。完整任务正在验证，不把几何通过或preview计为装载成功。

从工程根目录运行，新输出目录不可存在：

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher --headless \
 --config config/lab_cuvette_loading/Size_v1/standard.yaml \
 --output outputs/lab_cuvette_loading/Size_v1/NEW_LOADING_RUN
```

默认GUI，省略`--headless`。可通过配置`asset_id`或专用入口`--asset-id cuvette_xy_1000`选择注册资产，原座不变；其他尺寸的几何筛选必须先通过，不能继承10mm物理成功。几何重算、物理contact、输入材料几何检查和完整独立评分分开保存。

采集、训练及训练内自动验证都强制standard并禁用场景随机化；训练RNG种子另行固定。最终配置通过后生成frozen_scene.json再执行5次standard及20成功/20失败采集，本轮不运行random。当前开发preview不计入配额。旧Env_v1与全部历史资产输出保留。
