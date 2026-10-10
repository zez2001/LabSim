# Franka 空烧杯极简抓取 Demo

这个 demo 从空 USD stage 创建地面、灯光、固定桌子、一台 Franka、一个空烧杯和观察相机。使用 Lula 逆运动学计算关节位置目标，通过夹爪接触和摩擦抓取烧杯，再抬起并保持。运行时不打开或引用 `lab_001`。`run.sh` 保留原始极简演示；下面的任务管线通过项目已有工厂注册，接入 HDF5、ACT/Diffusion 训练和仿真推理。

## 启动

本机 GUI 启动命令：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/run.sh
```

GUI 默认在结果打印后继续显示并维持最后的机器人关节目标。关闭窗口或按 Ctrl+C 退出。`main` 保留上游原版，开发分支为 `codex/minimal-franka-beaker`。

启动脚本默认使用仓库同层的 `labutopia-env/bin/python`，本机版本为 Isaac Sim 5.1.0.0。其他机器可以通过 `LABSIM_PYTHON=/path/to/isaac/python` 指定已有环境，无需在此 demo 中安装新的 Python 依赖。

自动退出的 GUI 验证和截图：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/run.sh \
  --exit-on-result \
  --save-usd /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick/gui_scene.usda \
  --result-json /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick/gui_result.json \
  --screenshot /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick/gui_success.png
```

无界面运行使用 `--headless --exit-on-result`。将 `--timeout-seconds` 设为 1 可验证超时路径。任务预算按仿真时间计算，不包含 Isaac 启动和初始化；另有墙钟 watchdog，避免 GUI 暂停导致无限等待。

终端最终打印 `SUCCESS`、`FAIL` 或 `TIMEOUT`。退出码分别为 0、1、124；用户中断为 130。详细判据与测量值写入结果 JSON。

## 资产来源

Franka 引用仓库现有 `assets/robots/Franka.usd`，保留其真实关节、碰撞体和固定基座。Franka 包装类和 Lula 逆运动学来自已安装的 Isaac Sim，不调用 LabUtopia 原有机器人包装类附带的相机、传感器和数据管线。

烧杯来自上游提交 `8df72784265c375a327ffa3f0a0cf8c676f229a7` 的 `assets/chemistry_lab/lab_001/lab_001.usd` 中 `/World/beaker2/mesh`。检查发现它嵌在实验室层中，未引用独立 USD，材质绑定指向实验室 `/World/Looks/OmniSurface_Glass`。离线提取其 1698 个顶点、三角面索引，烘焙原始旋转，去除位置偏移后均匀缩放至 X 方向外轮廓 60 mm，实际高度约 72.1 mm，结果保存在 `assets/beaker.usda`。原网格的空腔和杯口保留，没有液体。

**烧杯视觉几何复用了原网格，不是生成的杯状代理模型。** 为方便观察，材质改成不透明蓝色 `UsdPreviewSurface`；碰撞使用 PhysX `convexDecomposition` 近似。质量设为 0.08 kg，开启重力和 CCD，静／动摩擦系数为 1.2／1.0，恢复系数为 0。尺寸、质量和摩擦是本 demo 的设定值，未经过真实烧杯标定；碰撞近似不适合作为液体或精细倾倒验证。

地面、灯光、桌子和相机由脚本生成。桌面高 0.74 m，桌板尺寸 1.2 × 0.8 × 0.08 m；桌子只有固定碰撞体，没有动态刚体。地面使用本地生成的平面和纯色材质，不依赖在线地面纹理。

## 场景和控制

机器人基座固定在 `[-0.30, 0, 0.74]` m，烧杯底部初始放在 `[0.20, 0, 0.741]` m。仿真步长为 1/120 秒，重力为 9.81 m/s²。初始化静置 1 秒后记录实际烧杯初始位置，以免把接触面沉降计入提升高度。

脚本执行靠近 3 秒、下降 2 秒、夹持 1.5 秒、抬起 2.5 秒、保持最多 3 秒。末端目标位置采用固定初始位置，移动阶段使用平滑插值。夹爪最大驱动力为每个手指 40 N，位置目标只施加到机器人关节。烧杯的位姿只在初始化时设定，运行阶段只读取其位置和接触力。

成功需要在保持阶段同时满足：

- 烧杯相对静置后的初始位置升高至少 0.05 m。
- 左右手指与烧杯的接触力分别大于 0.01 N。
- 上述条件连续满足至少 1 秒；任一条件失效，计时清零。

双侧接触要求比仅检查高度更严格，避免将弹飞或自由落体中的器皿算作成功。掉到桌下、被推出工作区、逆运动学不可达或保持阶段结束仍不满足条件时打印失败。超出任务仿真时间预算或墙钟 watchdog 时打印超时。

## 保存 USD

默认生成 `outputs/minimal_pick/scene.usda` 和 `outputs/minimal_pick/result.json`，可通过参数改路径。USD 是初始化静置后的场景，保存时间在任务动作开始之前。`Flatten` 把机器人和烧杯的 USD 引用展开，保存文件不包含完整实验室或对实验室的引用。渲染仍需 Isaac Sim 自带的 shader 实现。

在 Isaac Sim 中打开该 USD 可以检查场景和碰撞；USD 本身不包含 Python 任务状态机，重新执行抓取仍使用启动脚本。输出目录由项目现有 `.gitignore` 忽略，运行截图和 23 MB 左右的完整场景不提交到 Git。

## 实际验证

2026 年 10 月 10 日，本机 Isaac Sim 5.1.0.0、RTX 4090 上已运行初版：无界面物理抓取成功，最终升高约 0.1189 m；GUI 物理抓取成功，最终升高约 0.1193 m，双侧接触连续保持 1 秒，并保存了可查看的 GUI 截图和初始化场景 USD。

最终版本 GUI 复测成功，最终提升高度约 0.1192 m，连续双侧接触保持 1 秒，退出码为 0；纯色地面与成功截图已实际检查。1 秒任务预算的运行正确打印 `TIMEOUT` 并返回退出码 124。强制夹爪保持打开的物理负对照最终提升约 0 m、没有双侧接触，正确打印 `FAIL` 并返回退出码 1。导出 USD 重新加载后运行 120 个物理步，烧杯仍稳定在 0.74 m 桌面高度；场景不含任何外部 USD 引用，桌子固定碰撞、烧杯质量和场景重力检查通过。语法检查和 Shell 语法检查通过。

未验证其他机器／Isaac 版本、真实烧杯参数、液体行为、随机初始位置或统计成功率。

项目背景、完整规划书归档与本次工程范围见 [背景说明](../../docs/background/README.md)。

## 与其他任务相同的采集、训练和测试流程

任务名、控制器名和采集器名均为 `minimal_pick`，配置位于 `config/minimal_pick.yaml`。
新增文件为 `tasks/minimal_pick_task.py`、`controllers/minimal_pick_controller.py`、
`data_collectors/minimal_pick_collector.py`、`demos/minimal_pick/scene.py`、
`pipeline.py` / `pipeline.sh`、训练数据适配器和 ACT / DP 配置。
三个工厂新增注册项，`main.py` 为此配置调用独立场景入口；已有实验室配置的启动流程保持原样。
机器人和烧杯资产沿用上文所述来源。这里有两个训练相机，观察相机仍用于 GUI。

本机使用相同 Isaac Sim 环境。ACT 原实现导入 IPython，本次补齐了依赖；
复现安装命令是：

```bash
/home/wujing/Desktop/vla/labutopia-env/bin/python -m pip install \
  -r /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/requirements-training.txt
```

固定 `IPython==8.37.0` 和 Isaac Sim 所需的 `psutil==5.9.8`。
ACT 首次使用会下载原实现的 torchvision ResNet18 权重；本机已缓存。
远程推理复用仓库 `packages/openpi-client/src` 中已有的客户端。

### GUI 运行与记录

和其他任务一样通过主入口运行。默认采集一条演示，结束后关闭应用：

```bash
cd /home/wujing/Desktop/vla/LabSim
OMNI_KIT_ACCEPT_EULA=YES /home/wujing/Desktop/vla/labutopia-env/bin/python \
  main.py --config-name minimal_pick
```

指定采集数量、输出目录并保留 GUI 最终状态：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/pipeline.sh \
  --episodes 10 --keep-open
```

`--headless` 可用于批量采集，仍然渲染训练相机并保存录像；`--no-video` 只关闭录像保存，仍采集 RGB。
默认写入新的 `outputs/minimal_pick_pipeline/年月日_时分秒/`。
可以用 `--output /绝对路径/新目录` 指定位置，已有目录会报错，防止覆盖。
机器人与烧杯初始位置固定；每条演示重新 reset、静置，并重新计算初始高度。
重复采集不会自动增加场景多样性。

每次输出包括：

- `initial_scene.usda`：展开引用后的初始场景；USD 不含动作回放。
- `video/episode_0000.mp4`：两个训练视角并排的录像，512×256、60 fps。
- `dataset/episode_0000.h5`：逐帧训练数据和物理状态。
- `dataset/episode_data.hdf5`：按 `episode_0000` 等分组的成功演示汇总，可直接训练。
- `dataset/meta/episode.jsonl`、`episode_0000_result.json`、`summary.json` 和实际使用的 `config.yaml`。

终端打印 `SUCCESS` / `FAIL` / `TIMEOUT`，退出码分别为 0 / 1 / 124，中断为 130。
失败轨迹仍留在各自 H5 中，但不会进入成功演示汇总；异常中断的文件标记 `complete=false`。
成功判定在物理步上检查提升 ≥5 cm 和双侧接触连续 ≥1 秒，条件中断会清零。
模型和回放均只下发机器人关节位置目标，烧杯由物理接触运动。

### 数据契约

与项目原有训练管线同名的数据为 `camera_1_rgb`、`camera_2_rgb`，uint8 `[T,3,256,256]`；
`agent_pose` 和 `actions` 均为 float32 `[T,8]`，含 7 个机械臂关节和一个手指关节。
动作是绝对关节位置目标，夹爪目标会对称下发给两指。
采集频率 60 Hz，物理频率 120 Hz。
每个 `obs[t]` 在 `action[t]` 下发前获取；`actions[t]` 是该次实际下发的目标，
不是用下一帧测得的关节位置替代。两个物理步之后的状态保存在 `next_agent_pose` 和 `next_object_pose`。

还记录 `joint_positions`（含两个手指）、物体位姿（xyz+wxyz）、时间戳、接触力、提升高度、保持时长、done 和稀疏成功 reward。
训练适配器仅读取所需字段，按 episode 划分训练/验证集，动作分块在本条轨迹边界填充，
ACT 填充段会被 mask；归一化参数仅使用训练集。单条演示不会划出验证集。
新的适配器明确从 `actions` 读取监督目标，避免原适配器把测得的关节状态作为动作监督。
DP 使用原模型和工作空间，独立子类将输出块起点对齐到最后一帧观测对应的动作，不改变原任务的策略实现。

### ACT 或 Diffusion 训练

使用项目原有 `train.py` 和工作空间。默认数据路径指向本次已实际采集的演示，
训练时可替换为自己的采集目录：

```bash
cd /home/wujing/Desktop/vla/LabSim
/home/wujing/Desktop/vla/labutopia-env/bin/python train.py \
  --config-name=train_minimal_pick_act \
  task.dataset_path=/home/wujing/Desktop/vla/LabSim/outputs/minimal_pick_pipeline/verified_collect/dataset

/home/wujing/Desktop/vla/labutopia-env/bin/python train.py \
  --config-name=train_minimal_pick_dp \
  task.dataset_path=/home/wujing/Desktop/vla/LabSim/outputs/minimal_pick_pipeline/verified_collect/dataset
```

默认 batch size 为 8，W&B 日志关闭在线上传；正常训练按配置运行完整 epoch。
一次训练链路检查可额外加 `training.num_epochs=1 training.max_train_steps=2 training.max_val_steps=1`。
输出工作空间目录中的 `checkpoints/latest.ckpt` 包含模型、归一化器和配置；DP 可使用 EMA 权重。
两条固定初始位置演示与短训练仅用于验证工程链路，不能据此声称泛化或学习成功率。

### 在这个场景测试

专家测试就是上面的 `main.py --config-name minimal_pick`，同时记录演示。
对保存的动作轨迹重新进行物理仿真：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/pipeline.sh \
  --replay /home/wujing/Desktop/vla/LabSim/outputs/minimal_pick_pipeline/verified_collect/dataset/episode_data.hdf5 \
  --episode episode_0000 --keep-open
```

回放相同 60 Hz 的关节目标，不强制机器人测得的状态或器皿位姿。结果由重新仿真的接触与提升判定。
直接观看录像可用系统播放器打开 MP4，能暂停和拖动。

对训练检查点进行 GUI 测试：

```bash
bash /home/wujing/Desktop/vla/LabSim/demos/minimal_pick/pipeline.sh \
  --checkpoint /绝对路径/训练输出/checkpoints/latest.ckpt --keep-open
```

支持本项目 ACT / DP 工作空间检查点；不要求单独填写归一化器路径。
也可以像其他任务一样修改 `config/minimal_pick.yaml` 的 `mode: infer`，
设置 `infer.type: local` 和 `infer.policy_model_path` 后用 `main.py` 启动。
回放对应 `infer.type: replay`、`infer.replay_data_path` 和 `infer.episode`。
远程模型对应 `infer.type: remote`、`infer.host`、`infer.port` 和 `infer.n_obs_steps`；
继续使用原有 OpenPI WebSocket 协议，模型返回非空 `[动作数,8]` 绝对关节目标。
模型需要使用本任务的相机、状态和动作定义训练。

### 本轮实际验证与限制

2026-10-10，本机最终相机配置下 GUI 采集两条成功演示，均为 518 帧 / 8.633 秒，
最终提升 0.111837 m，连续双侧接触保持 1 秒；逐帧检查了 RGB 非空、画面变化、数据长度和录像可解码。
视频和数据位于 `outputs/minimal_pick_pipeline/verified_collect/`。
`video/episode_0000_preview.mp4` 为第一条录像的 H.264 浏览器预览版本；原始录像保留。

已验证成功动作回放、主入口 `main.py` 调用、ACT 和 DP 各两个训练批次的反向传播、
一个验证批次和检查点保存。ACT train loss 1.7060 / val loss 1.9119；
DP train loss 0.9396 / val loss 0.9758（仅工程检查数值）。
ACT 短训练检查点测试正确结束为 TIMEOUT；DP 短训练检查点测试正确结束为 FAIL，均未抓取成功。
远程接口通过本地 WebSocket 服务收发了 33 次观测/动作并完成成功抓取；
服务输出来自已记录动作，证明协议和执行兼容，未验证真实远程模型。
数据契约测试覆盖真实动作监督、episode 分割、边界填充和失败过滤。

尚未进行完整策略训练、策略学习成功率评估、LeRobot/OpenPI 数据转换与训练、
随机场景或真实硬件验证。本轮接入已有任务能力，不新增训练算法或 benchmark 评估系统。
`main` 分支保持上游原版；代码在 `codex/minimal-franka-beaker`，运行数据、视频和检查点由 `.gitignore` 排除。
