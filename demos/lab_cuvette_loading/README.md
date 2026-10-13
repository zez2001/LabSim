# 从来源架到仪器内装载：lab_cuvette_loading V0

代理场景重现所提供双视角视频的主要关系：白色多槽架、透明方形器皿、蓝色工作区、开盖白色仪器和黑色样品腔、腔内装载座、邻近结构、绿幕与双相机。使用现有 Franka 代理；真实“neo”机器人型号未确认。尺寸和物理参数属于未校准 V0；不模拟液体、光谱或化学反应。

```bash
cd /home/wujing/Desktop/vla/LabSim
# GUI：一条完整演示；结束后保持场景。不要重复使用已存在输出路径。
bash demos/lab_cuvette_loading/run.sh --keep-open --output outputs/lab_cuvette_loading/gui_NEW
# 兼容现有任务入口：默认 GUI、一次演示，自动创建时间戳目录。
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python main.py --config-name lab_cuvette_loading
# 固定标准布局，逐条新进程，顺序运行，不并行占用 GPU。
bash demos/lab_cuvette_loading/run.sh --headless --episodes 10 \
  --output outputs/lab_cuvette_loading/standard10_NEW
# 外观 A / 布局 B 独立检查。
bash demos/lab_cuvette_loading/run.sh --headless --mode appearance --seeds 120 \
  --output outputs/lab_cuvette_loading/appearance_NEW
bash demos/lab_cuvette_loading/run.sh --headless --mode layout --seeds 121 \
  --output outputs/lab_cuvette_loading/layout_NEW
# random 同时启用 A+B；冻结测试 seed 与采集 seed 分开。
bash demos/lab_cuvette_loading/run.sh --headless --mode random \
  --seeds 2000,2001,2002,2003,2004,2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019 \
  --output outputs/lab_cuvette_loading/random_test_NEW
bash demos/lab_cuvette_loading/run.sh --headless --mode random \
  --seeds 3000,3001,3002,3003,3004,3005,3006,3007,3008,3009,3010,3011,3012,3013,3014,3015,3016,3017,3018,3019 \
  --output outputs/lab_cuvette_loading/collection_NEW
# 原物理动作回放，必须恢复该 episode 的实际初态/采样布局。
bash demos/lab_cuvette_loading/run.sh --headless \
  --config outputs/lab_cuvette_loading/standard_demo_V0/config.yaml \
  --replay outputs/lab_cuvette_loading/standard_demo_V0/dataset/episode_0000.h5 \
  --replay-initial outputs/lab_cuvette_loading/standard_demo_V0/episode_0000_initial.json \
  --output outputs/lab_cuvette_loading/replay_NEW
# 新进程资产和复位检查。
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python demos/lab_cuvette_loading/reload_check.py \
  --episode-dir outputs/lab_cuvette_loading/standard_demo_V0 \
  --output outputs/lab_cuvette_loading/reload_NEW.json
# 数据、时序、独立离线判分、现有 ACT/DP adapter（不训练）。
../labutopia-env/bin/python demos/lab_cuvette_loading/audit.py \
  outputs/lab_cuvette_loading/standard10_verified_V0 \
  --output outputs/lab_cuvette_loading/audit_NEW.json
```

`--scene-only` 只展示/保存场景，不算完整任务；`--debug-material` 使用独立不透明杯资产，正式演示为透明版本。`--no-video` 只停 MP4，仍采集 RGB。新输出必须使用未存在目录，保护已有实验。批次因 Isaac 在同进程多次换空 Stage 后有渲染节点生命周期问题，采用一个 episode 一个新进程；子进程同时保存详细文件，汇总目录以硬链接收集，避免重复占用空间。默认均顺序运行。

配置：`config/lab_cuvette_loading/V0.yaml`；独立资产：`assets/lab_cuvette_loading/V0/*.usda`。run 会按该次配置重新导出资产。参数来源清单、冻结 hash、独立用途 seed 清单位于同一配置目录。后续换机器人必须提供匹配的模型/控制适配器，不能仅改 `robot.type` 绕过校验。

当前动作是 8D `[7 个手臂绝对关节目标(rad), 对称单指位置(m)]`；实际状态保存 9D，两个指关节均记录。固定 PhysX CPU/TGS、240 Hz 物理、60 Hz 控制、每动作保持 4 步。手臂驱动采用 force、力矩 87/12 N·m 上限，指驱动 8 N 上限；USD 角驱动增益按每度转换，运行时 tensor 增益用 SI/弧度，实际增益/上限读回保存在 effective.json。接触接口以当前 dt 将冲量换算成 N。

HDF5 保存 `camera_1_rgb/camera_2_rgb`（RGB、CHW uint8、256×256、每控制周期渲染）、`agent_pose`（8D 学习观测）、`actions`、`next_agent_pose`、`joint_positions`（9D）、时间戳、done、reward、phase_code；`privileged/*` 保存实际物体/TCP、下发 TCP、接触、几何重叠、目标误差和阶段进度。事件与逐物理步接触详细记录另存 JSON/JSONL。默认学习观测只有相机+agent_pose，不输入 oracle 真值。

时序为 obs_t → 下发 action_t → 4 个物理步（终止可提前）→ next_state。RGB_t 属于动作前，下一条记录即当前动作后的 RGB；最后一帧 MP4 使用动作后画面和同一动作后判分。视频中远离目标时显示 `outside target`，避免把目标高度投影误称为已经插入。脚本的 INSERT/RELEASE 等字样表示计划阶段，完整判分使用实际状态。

每 episode 留存 USD、config、源代码快照/sha、git 分支/提交/状态、实际初态、有效参数、采样 seed/layout、录像、H5、物理状态和事件。成功才进入 `episode_data.hdf5` 和 training_index；失败、初始化无效和进程失败保留在 failure_index 与总 summary。两个来源文件链接到同一 H5 不表示两条独立数据。重复 canonical 初态只能检验运行重复性，不能估计广泛场景成功概率。

现有 `policy.dataset.minimal_pick_dataset.MinimalPickDataset` 可直接读取本任务 8D 对称动作；任务 shape 配置已新增 `lab_cuvette_loading_act.yaml` / `_dp.yaml`。一次 adapter batch 读取只证明数据格式适配，不证明学习策略完成了任务。

独立判分/几何方法见 `docs/lab_cuvette_loading/task_spec.md`；真实数据接口见 `docs/lab_cuvette_loading/real_data_interface.md`。GUI 可以自由观察和选择 prim；执行标准完整任务必须从合法初态开始，手动拖动物体后的结果不进入正式统计。

额外提供与既有训练工作区兼容的 `policy/config/train_lab_cuvette_loading_act.yaml` 和 `_dp.yaml`；数据配置通过 Hydra 实际 compose/instantiate 并读取了 batch，本轮没有实例化或训练学习模型。今后可由根目录 `train.py --config-name train_lab_cuvette_loading_act` 或 `_dp` 调用，并按实际采集目录覆盖 `task.dataset_path`。
