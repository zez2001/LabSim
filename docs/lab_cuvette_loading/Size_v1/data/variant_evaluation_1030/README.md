# 十点三毫米独立尺寸验证配置

从已实际成功的 `loading_01/episode_0000/config.yaml` 通过同一 `resolve_asset_config` 注册规则派生 `config/lab_cuvette_loading/Size_v1/variant_evaluation_1030.yaml`，选择既有 `cuvette_xy_1030`。未创建或修改 USD、registry、standard.yaml 或冻结清单。

原A座、physics、control、场景、来源架、机器人、相机、夹持调度、判分、3秒稳定条件及现有装载轴偏移全部与成功10mm源配置相同。只改变已注册资产派生字段、准确的实验说明和 `experiment.run_role=variant_evaluation`；配置中没有 frozen_scene_manifest，不能计入最终10mm冻结采集配额。

本文件准备阶段未启动GPU或物理仿真，物理结果仍为未知。待5次standard结束后，由根agent顺序运行一次；不与现有Isaac进程并行。

```bash
bash demos/lab_cuvette_size_v1/run.sh --mode teacher --headless \
  --config config/lab_cuvette_loading/Size_v1/variant_evaluation_1030.yaml \
  --output outputs/lab_cuvette_loading/Size_v1/loading_1030_01
```

输出目录必须不存在。配置来源与产物SHA、全部字段差异、原座/physics/control等相等检查和四个受保护文件的未变哈希在 `config_comparison.json`。解析后的配置已通过YAML往返及重复asset解析幂等检查。
