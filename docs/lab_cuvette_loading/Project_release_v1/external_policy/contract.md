# π0.5 外部策略契约

当前环境为 `Project_release_v1`，使用固定 standard 场景及统一 RPC。策略接收双相机 RGB、机器人本体状态和任务文本，经显式动作转换调用环境执行器。推荐从 [当前使用指南](../README.md) 开始。

本接口采用独立部署的 `RLinf-Pi05-LIBERO-130-fullshot-SFT`。权重 SHA256 为 `4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683`，归一化统计 SHA256 为 `dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1`。服务校验 checkpoint 身份，执行器保存请求、实际动作和后继状态。该 checkpoint 在 LIBERO 上微调，当前以零样本方式接入 LabSim。

## 图像：环境、训练数据和 checkpoint 三层接口

| 层级 | 字段与规格 | 转换位置 |
|---|---|---|
| 原生相机与公开观察 | `images.side_camera`、`images.wrist_camera`；每路 `[480,640,3]`，HWC RGB `uint8`，0–255 | `CameraRig.get_images()` 读取两个独立传感器；任务 `_public_observation()` 原样复制，保留 4:3 比例 |
| H5 采集 | `side_camera_rgb`、`wrist_camera_rgb`；每帧 `[3,256,256]`，CHW RGB `uint8` | `_collector_state()` 调用 `policy_image()`：OpenCV `INTER_AREA` 拉伸为 256×256，再 HWC→CHW；这条分支用于数据记录 |
| 正常 ACT/DP reader | ACT batch 为 `[B,3,256,256]`；DP 为 `[B,n_obs_steps,3,256,256]`，`float32`，0–1 | `MinimalPickDataset.__getitem__()` 从 H5 取帧并除以 255，不再次缩放 |
| π0.5 适配器及 RPC 线上的服务输入 | `main_images`、`wrist_images` 为 `[1,480,640,3]`，NHWC RGB `uint8`；`states` 为 `[1,8] float32` | `Pi05LiberoAdapter.encode_observation()` 使用公开的原生图像；RPent `_encode_obs_libero()` 只添加 batch 维，没有先经过 H5 的 256×256 分支 |
| 已部署 checkpoint 的图像 processor | 三路 `[224,224,3] uint8`；前两路为实际相机，第三路全零且 mask=false | 安装的 `ResizeImages(224,224)` 调用 `openpi_client.image_tools.resize_with_pad()`，使用 PIL BILINEAR：640×480→224×168，再上下各填 28 像素黑边 |
| 模型 Observation | 每路 `[1,3,224,224] float32`，范围 −1 到 1 | 安装的 `Observation.from_dict()` 对 Torch uint8 张量作 NHWC→NCHW，并计算 `image / 255 * 2 - 1`；第三路无效 mask 保持 false |

`camera_meta.policy_transform`、`intrinsic_matrix_policy_256` 描述既有的 256×256 数据表示；当前 π0.5 适配器不使用该字段缩放公开图像。相机原生标定另行保存。帧读取时间、传感器时间和重复帧状态均保留。

真实服务输入、H5分支和部署processor的对应证据见[输入事实与文本审计](../internal_use/20261028/input_audit/README.md)。

## 机器人状态与任务文本

状态为 8 维 `float32`：相对机器人基座的 TCP xyz（m）、旋转向量（rad）、左指关节位置（m）、取负号的右指关节位置（m）。基座变换来自公开环境元数据。原 checkpoint 的 q01/q99 统计执行 quantile normalize，随后状态补零到 32 维。输入包含图像、本体状态与任务语言，不包含独立评分器的器皿或目标真值。

部署的 `pi05_libero` 配置为 `max_token_len=200`、`discrete_state_input=false`。PaliGemma SentencePiece tokenizer 先去首尾空白，将下划线和换行替换为空格，再执行 `encode(cleaned_text, add_bos=True) + encode("\n")`。该配置不添加 `Task/State/Action` 前缀，不把状态离散成文本，不添加 EOS。有效语言 mask 为 true，补齐位置为 false。

当前实际任务文本来自任务 `get_task_language()`，服务的 `inference.jsonl.task_descriptions` 保存实际传输文本。本地审计测得 264 个原始 tokens，保留前 200 个，尾部 64 个被截断；有效末尾落在 TCP 固定变换四元数中，后续四元数结尾及整手净空提醒未进入模型。文本及动作转换保持当前基线。完整有效 token IDs、mask、decode、文本 SHA256、tokenizer 文件 SHA256、处理源码位置和版本见审计文件。

以后启动此服务时，`effective_input_audit.jsonl` 按 request index 保存**原 processor 实际产生**的 token IDs/mask、截断核对、图像 shape/dtype/hash 及图像 mask。包装器只调用原 processor 一次，并将同一结果对象返回模型。

本地离线预检使用现有策略 Python，不加载权重、不启动模型服务。输入文件取自已关闭的模型服务目录；输出须为新目录：

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$LABSIM_POLICY_PYTHON" -m policy_backends.lab_cuvette_env_v1.input_audit \
  --model-path "$LABSIM_PI05_CHECKPOINT" \
  --input-npz "$MODEL_RUN/input_000001.npz" \
  --inference-log "$MODEL_RUN/inference.jsonl" \
  --request-index 1 --output outputs/input_audit_NEW
```

该入口限定已有本地 tokenizer/cache；缺少时明确报出所需路径。有效 processor 输入另存 NPZ，原服务输入与日志只读。

## 动作与执行

当前动作迁移配置仍为 [pi05_libero.yaml](../../../../config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml)；配置目录名称为兼容路径，运行环境明确选择 `Project_release_v1`。

1. 服务返回 7 维 LIBERO OSC 动作，已通过 checkpoint 统计反归一化。客户端将其裁至 `[-1,1]`，前三项乘 0.05 m、旋转三项乘 0.5 rad，再分别限幅到每轴 0.0005 m 与 0.004 rad。基座坐标转换为 world，调用 `ee_delta`。
2. 第七项正号关闭、负号张开。适配器按 ±0.008 m 更新有界单指目标，再发送双指总开口 0–0.08 m；夹爪力上限 8 N。
3. 策略 20 Hz，每动作 0.05 s，对应 60 Hz 的 3 个控制周期和 240 Hz 的 12 个物理步。模型 action horizon=10，返回 chunk=5，最多执行前 5 项后重新推理。
4. 每项动作绑定当前 episode、observation 和稳定 action ID，chunk 内使用前一项真实后继观察。拒绝、部分执行、终止或缺少后继时丢弃剩余动作。
5. 模型等待时物理暂停；推理前后核对 episode、step 和仿真时间。执行器保留共同的运动学限制、连续 IK、状态跟踪和接触锁存。

`target_reached` 为仿真 TCP 执行端点标志，使用当前 1 mm / 0.5° 容差；精细控制诊断结果的测量对象为空夹爪仿真 TCP。任务成功由独立评分器判定。触觉标量是器皿过滤后的左右指法向接触向量模长。实际双指关节命令及力限制由采集器另存。

## 回执、记录与结束

- 模型服务：实际线输入 NPZ、图像/状态 hash、有效输入审计、输出 NPY、推理用时与 GPU 内存。
- 策略客户端 `policy_events.jsonl`：返回数组、动作转换、请求、回执、后继 ID 和推理暂停检查。
- 环境 `action_receipts.jsonl`：实际执行周期、部分执行、目标到达和安全停止；H5 的 `control_auxiliary/command_q` 保存最终实际 9 维关节命令。
- `executed_actions` 只统计取得回执且推进了物理的动作。模型服务输出是 checkpoint 反归一化后的动作数组。
- `--max-simulation-s`、`--max-model-requests`、`--max-actions` 分别限制实际仿真时长、推理次数和动作请求数。失败评测与服务异常分别分类。
- `finalize_episode` 结束当前集；RPC `shutdown` 关闭共享环境。既有安全终止结果保留。
- 完整 chunk 的 canonical 请求有回执缓存；同请求重试返回原结果，部分 chunk 或异常中断不通过重试补执行。

## 本机部署与启动

使用现有隔离的 RPent Python 和 checkpoint，不安装进 Isaac Python：

```bash
export RPENT_REPO_ROOT=/path/to/rpent
export LABSIM_POLICY_PYTHON="$RPENT_REPO_ROOT/.venv/bin/python"
export LABSIM_PI05_CHECKPOINT=/path/to/RLinf-Pi05-LIBERO-130-fullshot-SFT

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$LABSIM_POLICY_PYTHON" -m policy_backends.lab_cuvette_env_v1.pi05_server \
  --model-path "$LABSIM_PI05_CHECKPOINT" --port 8098 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_model_NEW

./labsim serve --project-version Project_release_v1 --headless \
  --record-mode eval --record-purpose policy_evaluation --port 8097 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_env_NEW

"$LABSIM_POLICY_PYTHON" -m policy.backends.rpent_compat --backend pi05 \
  --env-endpoint http://127.0.0.1:8097 --vla-endpoint http://127.0.0.1:8098 \
  --max-simulation-s 20 --max-model-requests 80 --max-actions 400 \
  --output outputs/lab_cuvette_loading/Project_release_v1/pi05_policy_NEW
```

服务使用 CUDA；一个策略模型和一个 Isaac 进程按评测调度共用 GPU。输出必须为新目录。关闭使用 RPC `shutdown`，等待数据和进程完成闭合后再构建索引。

## 验收与历史记录

- [发布版实际连续模型运行](pi05_standard_01_closed_audit/summary.json)：69 次推理、341 个动作后安全终止，完成记录回读。
- [正式数据入口读取结果](../validation/official_pi05_dataset_check_clean_4a71635/failure.json)。
- [2026-10-27 部署预检快照](preflight_20261027.json)。
- 早期五动作连通性实验保留在 [Project_v1 历史证据](../../Project_v1/policy_evidence/optional_physics_regressions_actual.json)。
