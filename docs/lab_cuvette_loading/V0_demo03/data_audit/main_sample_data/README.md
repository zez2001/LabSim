# 与最终主片同源的两个真实数据样本

本目录的 `batch_sample.npz` 来自最终主片采用的同一次连续运行：`random10_20261020_01/seed_8000/trial_00`。它包含 14 s（EXTRACT）和 33 s（INSERT）两个真实控制时点的样本，**不是完整 episode**。旧 `sample_data/` 中 dev_03 的历史样本保持原样。

完整原始 H5 位于：

`/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_demo03/random10_20261020_01/seed_8000/trial_00/dataset/episode_0000.h5`

同源原始主片：

`/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_demo03/random10_20261020_01/seed_8000/trial_00/main.mp4`

`verification.json` 保存视频、原 H5、独立评分及样本 SHA256；两个样本由现有 `policy.dataset.minimal_pick_dataset.MinimalPickDataset` 实际读取。动作逐元素与原 H5 一致，RGB 反量化为 uint8 后与原像素一致，agent_pose 逐元素一致，NPZ 使用 `allow_pickle=False` 重载通过。源 H5 未修改。

数组包含：

- `obs_camera_1_rgb`、`obs_camera_2_rgb`：各 `[2,3,256,256]`，float32、RGB/255。
- `obs_agent_pose`：`[2,8]`，七个机械臂关节角（rad）及对称夹指位置（m）。
- `action`：`[2,16,8]`，各样本起连续十六个绝对关节位置命令，前七维 rad，末维 m。
- `is_pad`：`[2,16]`，此次均为 false。
- `source_control_indices`、`source_timestamps_s`、`source_phases` 及标量字符串 `metadata_json`：追溯信息。

这只是经明确适配场景限定的仿真数据资格。`native_pair_success=false`、`real_calibrated=false`；没有训练模型，也不进入原 CAD 配套验证的成功索引。

在 LabSim 工程根目录复现已有加载器验收时，输出路径必须是新目录：

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.data_check \
  --episode outputs/lab_cuvette_loading/V0_demo03/random10_20261020_01/seed_8000/trial_00/dataset/episode_0000.h5 \
  --score outputs/lab_cuvette_loading/V0_demo03/random10_20261020_01/seed_8000/trial_00/independent_score.json \
  --output outputs/lab_cuvette_loading/V0_demo03/data_audit/NEW_MAIN_LOADER_INDEX
```

现有验收报告为上级目录 `random8000_actual_loader.json`。完整控制时序见 `../random8000_trajectory/`。需要重新导出这两个样本时使用上级 `export_actual_batch.py --help`，无需启动 Isaac Sim。
