# π0.5 外部策略接入契约

本入口使用已经部署的 `RLinf-Pi05-LIBERO-130-fullshot-SFT`，没有进行 LabSim 训练或微调。LIBERO 到本任务的动作转换属于显式工程迁移，不能解释为两个仿真器动力学等价。预检记录见 [preflight_20261027.json](preflight_20261027.json)；该预检不代表已经完成本轮真实模型运行，实际结果以本轮独立运行证据为准。

## 模型与观察

- 权重 SHA256：`4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683`。
- 归一化统计 SHA256：`dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1`。客户端同时检查这两个摘要与端点身份。
- 侧视、腕视是实际独立传感器的 HWC RGB `uint8` 图像。客户端添加 batch 维；继承的 π0.5 处理链执行 224×224 保持比例填充缩放。没有把腕视复制为侧视。模型中的第三路零图像明确 masked，不是第三个相机。
- 模型状态为 8 维 `float32`：相对机器人基座的 TCP xyz（m）、旋转向量（rad）、左指关节位置（m）、取负号的右指关节位置（m）。实际机器人基座变换来自公开环境元数据，允许显式覆盖并记录。
- 模型接收图像、机器人状态及任务语言；相机标定另存审计记录，不增加器皿或目标座真值。公共触觉存在于环境接口，但这个 LIBERO 8 维编码没有额外拼入触觉。
- 原模型处理链使用 checkpoint 内的 q01/q99 quantile normalize/unnormalize。服务返回的 7 维动作已经恢复成 LIBERO 数据的 OSC 幅度约定；客户端不再进行一次统计反归一化。这里所称“模型原始动作”指该服务原输出，不是内部 diffusion latent。

## 动作及实际执行

显式迁移配置为 [pi05_libero.yaml](../../../../config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml)。本轮没有改变它的数值。

1. 将返回动作裁到 `[-1,1]`。前三项按 LIBERO 的 0.05 m 标度、旋转三项按 0.5 rad 标度转换，再按每轴 0.0005 m、0.004 rad 工程限幅。从机器人基座旋转到 world，发送 `ee_delta`。
2. 第七项遵循原 Panda 的正号关闭、负号张开语义。通过有界、带状态的单指位移 ±0.008 m 更新 0–0.04 m 单指目标，再发送双指总开口 0–0.08 m。力上限保留 8 N。它不是把第七个数直接当成米或关节角。
3. 策略动作频率 20 Hz，每动作 0.05 s，对应环境 60 Hz 的 3 个控制周期及 240 Hz 的 12 个物理步。模型 action horizon=10、返回 action chunk=5，最多执行前 5 项后重新推理。
4. 每项动作绑定实际当前 episode/observation，并有稳定 action ID。chunk 内每项使用前一项的实际后继观察。拒绝、部分执行、无可用后继或终止会丢弃剩余项，不自动补完或重新执行。
5. 模型等待时不推进物理。客户端在真实推理前后比较 episode、step、仿真时间；环境被其他客户端改变时拒绝旧 chunk。

同一环境执行器仍有共同的 EE 距离、速度、旋转及关节运动学限制，并运行原有机器人状态跟踪补偿与 GenericContactHold。π0.5 的每轴迁移限幅比公共 EE 单次上限更小；不同动作空间不能概括成相同数值限幅。GenericContactHold 只根据实际双指接触维持目标，不使用器皿位姿，不是抓取任务宏。其实际下发值由采集器保存，不能用适配器请求替代。

`target_reached` 仅表示实际 TCP 端点符合执行器当前的 1 mm / 0.5° 容差，不表示抓取、插入或任务成功，更不是 0.1 mm 的实物精度。在线独立评分器根据物理状态判定任务。触觉标量是器皿过滤后的双指法向接触向量模长，不等于全部触觉、力矩、摩擦或底部承托测量。

## 证据分层与结束

- 模型服务保存实际输入 NPZ、逐路 shape/dtype/SHA256、输出 NPY、原返回数组、推理用时及 GPU 内存。
- 策略客户端 `policy_events.jsonl` 保存完整返回数组、选择的 chunk、原动作、适配请求、action receipt、真实后继 ID、仿真时间及推理暂停检查。
- 环境 `action_receipts.jsonl` 保存实际执行周期、部分执行、目标到达和安全停止；H5 的 `control_auxiliary/command_q` 保存最终实际 9 维关节命令。常规 8 维训练动作保持既有语义。
- `executed_actions` 只统计取得回执且确实推进的动作；拒绝的零步请求不计入。未获回执的请求不猜测执行量，关闭后的环境记录才是最终依据。
- `--max-simulation-s`、`--max-model-requests`、`--max-actions` 分别限制实际仿真时长、模型次数及动作请求数。模型等待不消耗仿真时间。任务失败可以是有效评测，服务异常单独分类。
- `finalize_episode` 只结束当前集，不关闭共享环境；`env.close` / `shutdown` 用于结束服务。旧安全终止结果不能被随后发生的客户端错误改写。
- release RPC 对完整 chunk 的 canonical 请求建立回执缓存；同请求重试返回原结果，不随新状态重新展开。部分 chunk 及异常中断不得通过重试恢复。

## 本机已有部署的启动方式

以下为配置完成后的正式命令；真实验收状态另见本轮运行结果。路径由使用者替换为已有的隔离模型运行环境和 checkpoint，不安装进 Isaac Python。

```bash
"$LABSIM_POLICY_PYTHON" -m policy_backends.lab_cuvette_env_v1.pi05_server \
  --model-path "$LABSIM_PI05_CHECKPOINT" --port 8098 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_model_NEW

./labsim serve --project-version Project_release_v1 --headless \
  --record-mode eval --port 8097 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_env_NEW

"$LABSIM_POLICY_PYTHON" -m policy.backends.rpent_compat --backend pi05 \
  --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
  --max-simulation-s 20 --max-model-requests 80 --max-actions 400 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_policy_NEW
```

本机原部署为 `/home/wujing/Desktop/vla/rpent/.venv/bin/python` 与其 `checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT`。模型服务明确要求 CUDA；与一个 Isaac 进程组成同一评测，须统一调度 GPU。所有输出目录必须为新目录。没有自动训练、自动 checkpoint 下载或付费 API 回退。
