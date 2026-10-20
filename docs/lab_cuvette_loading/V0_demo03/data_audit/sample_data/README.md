# 两个真实采样组成的 batch

`batch_sample.npz` 是 dev_03 同一条成功物理轨迹中 **14.0 s EXTRACT** 和 **33.0 s INSERT** 两个真实采样，经现有 `MinimalPickDataset` 读取并 collate 的 batch。它不是完整 episode，也不是两次实验。未训练或运行优化器。

完整原始 H5 在本机：

`/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/V0_demo03/dev_03/trial_00/dataset/episode_0000.h5`

完整 episode 含 3705 个 60 Hz 控制帧及双路 RGB；本小文件仅约 360 KB。动作与源 H5 逐元素一致，RGB 反量化后与源像素一致；源 H5 前后哈希未变。来源、SHA256 和实际检查见 `verification.json`。

字段：

- `obs_camera_1_rgb`、`obs_camera_2_rgb`：`[2,3,256,256]`，float32，RGB，范围 0—1。
- `obs_agent_pose`：`[2,8]`，7 个机械臂关节位置（rad）和一个手指位置（m）。
- `action`：`[2,16,8]`，每个采样起的 16 个真实未来关节绝对目标，7 个机械臂关节（rad）加对称手指目标（m）。
- `is_pad`：`[2,16]`，均为 false。
- `source_control_indices`：840、1980；`source_timestamps_s`：14.0、33.0。
- `metadata_json`：来源、模式、槽位、目标座、资产哈希和动作语义。

模式为 `video_demo_adapted`，`native_pair_success=false`、`real_calibrated=false`；成功及数据资格只适用于本次明确的工程改造场景。

无需仿真即可查看小样例：

```python
import json
import numpy as np

with np.load("docs/lab_cuvette_loading/V0_demo03/data_audit/sample_data/batch_sample.npz",
             allow_pickle=False) as sample:
    print(sample["action"].shape)
    print(json.loads(str(sample["metadata_json"])))
```

在仓库根目录复现完整 H5 的现有 loader 验收，输出路径须换为新目录：

```bash
../labutopia-env/bin/python -m demos.lab_cuvette_demo03.data_check \
  --episode outputs/lab_cuvette_loading/V0_demo03/dev_03/trial_00/dataset/episode_0000.h5 \
  --score outputs/lab_cuvette_loading/V0_demo03/dev_03/trial_00/independent_score.json \
  --output outputs/lab_cuvette_loading/V0_demo03/data_audit/NEW_LOADER_CHECK
```

成功 loader 验收见上一层 `dev_03_actual_loader.json`。外链索引依赖原始 H5 路径；本 NPZ 自身可以独立读取。
