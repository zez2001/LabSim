# π0.5 冻结执行方案与输入核查

本轮使用 **RLinf-Pi05-LIBERO-130-fullshot-SFT → 既有 RPent HTTP RPC → LabSim Project_release_v1**。这是 LIBERO 微调 checkpoint 在当前固定器皿装载任务上的直接迁移，保留现有图像、状态、动作转换及 chunk 执行。身份与逐文件 SHA256 见 [pi05_identity.json](pi05_identity.json)。

此文档记录运行前的只读核查和拟冻结规格。历史运行仅支撑接口事实，当前轮次的真实调用、输入和结果以新输出目录及冻结协议为准。

## 模型身份和本机部署

- 模型：`RLinf-Pi05-LIBERO-130-fullshot-SFT`。
- 来源入口：[RLinf 模型仓库](https://huggingface.co/RLinf/RLinf-Pi05-LIBERO-130-fullshot-SFT)。本机 RPent `README.zh-CN.md:138` 指向此仓库；本地未保留可确认的 Hub 下载 revision，因此以完整文件 SHA256 固定身份。
- 本机 checkpoint：`/home/wujing/Desktop/vla/rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT`。
- 权重：`model.safetensors`，7,473,091,464 字节，SHA256 `4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683`。
- 归一化：`physical-intelligence/libero/norm_stats.json`，SHA256 `dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1`。
- RPent 提交：`0d72dfac1e75417564e220e31ba7e4b5d8e83665`。独立解释器 `/home/wujing/Desktop/vla/rpent/.venv/bin/python`，Python 3.11.16、Torch 2.7.1、rpent-openpi 0.2.2、rpent-rlinf 0.3.0。
- `metadata.pt` 静态 pickle 字符串包含 `full_sft_pi05_libero_130_fullshot`、`data/libero_130_fullshot`、`physical-intelligence/libero` 和 `checkpoints/torch/pi05_base`；核查未执行 pickle。工程未进行 LabSim 微调；上游基座完整训练集及数据成员关系未知。“直接迁移”仅指当前任务没有新训练。

核查时 GPU 为 RTX 4090，驱动报告 49,140 MiB 总显存，桌面约占 1,662 MiB；8097、8098 端口无服务，也没有已运行的 Isaac/model 进程。这是运行前时点快照，正式资源占用另行记录。

## 输入：原生相机、数据 reader 与 checkpoint 分支

环境公开观察为侧视和腕视两个独立 RGB 传感器，各自 `uint8 [480,640,3]`，HWC、0–255。

π0.5 适配器的实际输入链路：

1. `Pi05LiberoAdapter.encode_observation()` 从公开观察取两路原生 RGB，以及机器人 TCP、指关节和 `task_language`。
2. RPent `_encode_obs_libero()` 加 batch 维：`main_images`、`wrist_images` 均为 `uint8 [1,480,640,3]`；`states` 为 `float32 [1,8]`；`task_descriptions` 为单元素字符串列表。`extra_view_images=None`。
3. 原 checkpoint processor 用 PIL BILINEAR 保持比例：640×480 → 224×168，再上下各补 28 像素。两实际视角映射到 `base_0_rgb`、`left_wrist_0_rgb`；`right_wrist_0_rgb` 为全零并且 mask=false。
4. `Observation.from_dict()` 转为每路 `float32 [1,3,224,224]`，数值 `image/255*2-1`。

H5 记录分支另用 OpenCV `INTER_AREA` 拉伸到 256×256、HWC→CHW，正常 ACT/DP reader 再除以 255。**H5 的 256×256 表示不参与本 RPC 输入链路。**

8 维机器人状态依次是机器人基座坐标下 TCP xyz（m）、相对旋转向量 xyz（rad）、左指位置（m）、取负号的右指位置（m）。服务使用原 checkpoint 的 q01/q99 quantile 统计，之后补零至 32 维。分布外状态可能超出 −1 到 1；当前未新增裁剪或重归一化。

模型输入不含器皿真值位姿、精确座口误差、Teacher waypoint、Progress 阶段/进度或 scorer 结果。`policy_observation()` 使用白名单；最终 `encode_observation()` 仅编码两图、上述 8 维状态和任务文本。评测日志可以保存其他信息，但不将其自动送入 checkpoint。

## 实际任务文本与截断

文本来源是环境 `get_task_language()` → `observation.task_language` → 线上 `task_descriptions`，每次服务调用在 `inference.jsonl` 保存实际文本。

已关闭的发布版真实输入及当前相同 processor 的审计证据位于：

`docs/lab_cuvette_loading/Project_release_v1/internal_use/20261028/input_audit/evidence/request_000001/audit.json`

- canonical 文本 SHA256：`08cf802a689dd18cbc0eff89749b821d966b6a0106907dc779426720f8dd8a65`。
- tokenizer：`openpi.models.tokenizer.PaligemmaTokenizer`，SentencePiece 模型 SHA256 `8986bb4f423f07f8c7f70d0dbe3526fb2316056c17bae71b1ea975e77a168fc6`。
- 处理：去首尾空白、下划线和换行改空格，`encode(text, add_bos=True) + encode(newline)`；不加 `Task/State/Action` 前缀、不把 state 离散进文本、不加 EOS。
- 原始 264 tokens，模型上限 200，保留 200、截断末尾 64。
- 核心完整任务“来源架 A1 抓取 → 搬运到远铰链内部座 → 插入 → 支撑交接 → 双指打开 → 撤离 → 稳定”全部位于保留前缀。被截部分是静态 TCP 四元数尾部和整手净空提醒。
- 实际 retained decode、完整 token IDs、mask 与被截 decode 在本目录身份 JSON 中完整保存。

本轮保留当前 canonical 文本，不以文本缩短优化策略表现。新预检仍需核对实际 `effective_input_audit.jsonl` 的文本 hash、tokens 和核心指令；历史审计不计作本轮模型调用。

CPU 本地预检可复用已关闭输入；输出必须是新目录，不加载权重、不启动服务：

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/home/wujing/Desktop/vla/rpent/.venv/bin/python \
  -m policy_backends.lab_cuvette_env_v1.input_audit \
  --model-path /home/wujing/Desktop/vla/rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT \
  --input-npz outputs/lab_cuvette_loading/Project_release_v1/pi05_standard_01_model/input_000001.npz \
  --inference-log outputs/lab_cuvette_loading/Project_release_v1/pi05_standard_01_model/inference.jsonl \
  --request-index 1 --output outputs/lab_cuvette_loading/Policy_eval_v1/input_audit_NEW
```

## 原生动作和执行契约

服务构造 `OpenPi0ForRLActionPrediction`，原配置 horizon=10、内部 action_dim=32、实际输出 chunk=5、环境 action_dim=7、5 个去噪步。`mode=eval` 的去噪步骤选择 flow ODE，初始噪声仍由 Torch 采样；不能仅凭 eval 名称宣称动作完全确定。

RPC 返回 `float32 [1,5,7]`，客户端去 batch 得 `[5,7]`。输出已经过 checkpoint 的 action 反归一化，不能再反归一化一次。

当前发布动作配置保留兼容路径：

`config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml`

每行先裁至 `[-1,1]`，xyz 乘 0.05 m、旋转向量乘 0.5 rad，再限到每轴 ±0.0005 m、±0.004 rad；基座方向旋转到 world，提交 `ee_delta`。夹爪动作 >0.05 为闭合、<−0.05 为张开，单指状态目标每步变化 0.008 m，限于 0–0.04 m，发送双指总开口；力限制 8 N。环境继续使用共同的实际接触锁存和安全执行器。

策略 20 Hz，每行 0.05 s，等于 3 个 60 Hz 控制周期、12 个 240 Hz 物理步。一组最多执行 5 行，即 0.25 s，再重新观察推理。每行基于上一行真实后继观察执行；拒绝、部分执行或终止丢弃剩余 chunk，不自动重放。

必须使用 `policy.backends.rpent_compat` 或显式传入上述配置。裸 `LiberoTransferContract()` 的历史默认是 2 mm/0.02 rad，不等于本轮冻结的 0.5 mm/0.004 rad。该差异通过配置选择解决，不更改动作转换数值。

## 运行、有限预算与 reset

以下是当前入口模板，`NEW` 必须改为新的独立输出；正式顺序、seed、外层墙钟保护由本轮协议统一规定。

```bash
# 模型：已有独立 RPent 环境，进程内离线运行；不修改 Isaac Python。
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/home/wujing/Desktop/vla/rpent/.venv/bin/python \
  -m policy_backends.lab_cuvette_env_v1.pi05_server \
  --model-path /home/wujing/Desktop/vla/rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT \
  --port 8098 --seed 0 \
  --output outputs/lab_cuvette_loading/Policy_eval_v1/pi05_model_NEW

# 一个 Isaac RPC 环境，与该模型共用 GPU；勿同时运行第二个 Isaac 任务。
./labsim serve --project-version Project_release_v1 --headless \
  --record-mode eval --record-purpose policy_evaluation --progress --port 8097 \
  --output outputs/lab_cuvette_loading/Policy_eval_v1/pi05_env_NEW

# 正式单集：相同170s任务上限，保留原chunk/频率/安全规则。
/home/wujing/Desktop/vla/rpent/.venv/bin/python \
  -m policy.backends.rpent_compat --backend pi05 \
  --policy-config config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml \
  --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
  --subtask loading --layout-mode standard --seed 0 \
  --max-simulation-s 170 --max-model-requests 700 --max-actions 3500 \
  --output outputs/lab_cuvette_loading/Policy_eval_v1/pi05_policy_NEW
```

短真实接口预检使用相同入口，将 policy 限制改为 `--max-model-requests 1 --max-actions 5 --max-simulation-s 0.25`；预检环境用途明确选 `lifecycle_diagnostic`，与正式 `policy_evaluation` 分开。任务未成功或正常安全终止不构成接口错误。

服务 `vla.predict` 超时 120 s、模型就绪等待 60 s、metadata 30 s、环境 reset/finalize 120 s。既有 runner 没有自动策略重试；整集墙钟保护需由本轮外层监督器固定并记录。默认 100 次推理只覆盖最多 25 s，不能照搬其默认值冒充完整 170 s 任务预算。

模型推理时物理暂停；推理前后的 episode/step/time 必须一致。每集新 runner 构造新 adapter，清空 episode 身份、推理计数和夹爪状态目标；动作余队列不会跨集。模型本身按当前单帧观察独立预测，未注册 `reset_session`。

`--seed` 在模型服务构造时调用 `torch.manual_seed`；环境 reset seed 与模型 seed 是两个事项。服务支持可选 `inference_seed`，但当前 stock adapter 仅发送 `mode=eval`。复用模型服务时 RNG 流继续，不能把环境 seed 宣称为 checkpoint 的逐集 seed。可以按预先声明的固定服务顺序记录 RNG 消费，或逐集重启模型并记录 startup seed。

## 记录与验收关口

模型侧保留输入 NPZ、实际 processor 审计、反归一化后输出 NPY、推理耗时和 CUDA peak；policy 侧保留返回 chunk、转换值、每行请求、执行回执及后继 ID；环境保留配置、原判分、H5、实际关节命令、侧/腕视视频和 Progress v1.2。

短预检要检查真实调用、相机/状态/文本、动作返回与执行、安全终止及记录关闭；正式各集另检查 episode 身份、时间和状态邻接、全部 finalize 事件、视频解码、原评分与数据资格。此处历史接口证据仅供核查，不计入新 10 集正式统计。

当前必须处理的是正确配置选择、显式完整任务预算、当前真实 token/shape 审计和逐集 reset/seed 口径。checkpoint、图像/状态归一化、动作映射、chunk、控制及任务判据保持基线。
