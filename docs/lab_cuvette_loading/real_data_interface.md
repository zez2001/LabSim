# 真实数据导入接口

当前没有真实尺寸、动作/状态或标定记录。接口用明确标记的合成夹具检查；不构成真实校准证据。机器人照片型号未确认，当前 embodiment ID 为 `franka_proxy`。

参数导入：JSON 包含 `version`（必须新建，例如 V1）、`purpose`（calibration 或 model_selection）及 `parameters`。每项为 `name`（V0.yaml 点路径）、`value`、`unit`、`source`、`source_type`。支持 m/mm/cm、kg/g、rad/deg、s/ms、Hz 及配置声明的力/力矩/增益/惯性单位。Isaac 相机 focal_length 配置单位为 cm，导入会按配置单位换算；关节 max_velocity/max_effort 的混合向量需明确使用 mixed_SI（前7项rad/s或N·m、末2项m/s或N）。输出新的 config.yaml 与逐项旧值/新值/来源历史；不覆盖 V0，`calibrated` 保持 false。来自 final_validation 的数据禁止调参。导入后重新检查 standard、random 分布、判分、旧数据和回放；大量资产/控制变化需重新采集。

轨迹导入 JSON 必须提供：

- `purpose`: calibration/model_selection/final_validation；独立划分真实数据用途。
- `robot_type`: franka_proxy；其他机器人绝对关节序列直接拒绝，先实现匹配机器人和控制适配器。
- `world_frame`: LabSim_Z_up_metres，`quaternion_order`: wxyz。不同坐标系先独立测定变换并显式转换；接口不会猜测。
- `joint_names`: panda_joint1…7、panda_finger_joint1/2；允许不同排列，按名称重排。
- `angular_unit`: rad/deg；`linear_unit`: m/mm；`time_unit`: s/ms。
- `action_semantics`: absolute_joint_position；`timestamps` 严格递增；`joint_states` 和 `commands` 为 N×9（两指明确）。可附 `events`、`results`。

静态模式 `static_geometry`：放置机器人记录状态，只用于静态几何和画面检查，不输出物理任务成功。响应模式 `command_response`：只在起点设置状态，随后下发记录的机器人命令、物理积分并保存仿真响应；不会设置器皿轨迹。时间戳须落在 physics_dt 网格，非整倍数需显式重采样。比较输出区分状态、命令、仿真状态和单位，不将“真实状态被放入仿真”当作动力学一致证据。

```bash
cd /home/wujing/Desktop/vla/LabSim
../labutopia-env/bin/python demos/lab_cuvette_loading/real_import.py \
  --record /absolute/path/record.json --output outputs/lab_cuvette_loading/import_NEW
../labutopia-env/bin/python demos/lab_cuvette_loading/real_import.py \
  --measurements /absolute/path/measurements.json --output outputs/lab_cuvette_loading/V1_candidate_NEW
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python demos/lab_cuvette_loading/real_compare.py \
  --record /absolute/path/record.json --mode static_geometry --headless \
  --output outputs/lab_cuvette_loading/static_NEW
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python demos/lab_cuvette_loading/real_compare.py \
  --record /absolute/path/record.json --mode command_response --headless \
  --output outputs/lab_cuvette_loading/response_NEW
```

`V1` 只表示参数版本。独立真实验证通过前不能标记为已验证模型；最终验证数据不能参与参数或模型选择。本轮不操作真机、不训练模型、不通过改变 rest_offset 或放宽成功阈值匹配结果。
