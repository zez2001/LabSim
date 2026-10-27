# 输入契约核查：2026-10-28

这是当前使用契约的技术证据；正常接入从 [外部策略契约](../../../external_policy/contract.md) 或 [当前使用指南](../../../README.md) 开始。

## 结果

实际模型服务输入是 `[1,480,640,3]` HWC RGB `uint8`，而非先经过 256×256。256×256 CHW 表示属于 H5/ACT/DP 记录和训练读取分支。该区分已同步到策略契约和可选策略指南。

部署的 `pi05_libero` 配置使用 `max_token_len=200`、`discrete_state_input=false`。真实服务首末请求的同一任务文本经已安装的 tokenizer 得到 **264 tokens → 保留 200、截断 64**。有效文本末尾止于 TCP 固定变换四元数的 `[0.0, 0.0, 0.0,`，丢弃的后缀包含 `1.0] in wxyz order` 及整手净空提醒。模型任务输入配置和文本本轮保持原样；这些事实说明实际有效输入范围，不单独解释策略任务结果。

| 核查项 | 实测结果 | 证据 |
|---|---|---|
| 保存的真实线输入 | 69 份 NPZ 的 shape、dtype、逐数组 SHA256 全部匹配原推理回执；侧、腕每路 `[1,480,640,3] uint8`，状态 `[1,8] float32` | [全部 69 次输入检查](evidence/all_69_wire_input_checks.json) |
| H5 图像分支 | `[1021,3,256,256] uint8`；两路 H5 首帧都等于对应真实线输入首帧经 OpenCV INTER_AREA 拉伸并转 CHW 的结果；旧相机名为同一 H5 对象的 hardlink | [汇总](evidence/summary.json) |
| checkpoint processor | 安装的 PIL BILINEAR resize-with-pad：640×480→224×168，上下各填 28 黑像素；三路 `[224,224,3] uint8`，第三路零图像 mask=false | [首请求审计](evidence/request_000001/audit.json)、[末请求审计](evidence/request_000069/audit.json) |
| Torch Observation | `[1,3,224,224] float32`，像素按 `/255*2-1` 转到 −1…1 | 同上，`torch_observation_images` |
| tokenizer | 安装的 `openpi.models.tokenizer.PaligemmaTokenizer`，SentencePiece；二进制 SHA256 `8986bb4f423f07f8c7f70d0dbe3526fb2316056c17bae71b1ea975e77a168fc6` | 同上，源码、版本和哈希 |
| 文本格式 | 清理首尾空白、下划线和换行；`encode(cleaned, add_bos=True) + encode(newline)`；没有 Task/State/Action 包装，状态不加入文本；BOS=2、EOS=1 未添加、PAD=0 | 同上，原始及有效 token IDs、mask、decode |
| 有效 token | 200 个有效位置，无 padding，mask 全 true；原 tokenizer 输出与独立格式核对逐项一致 | 同上，`output_matches_installed_formatting=true` |
| 服务只读审计包装 | 用实际部署 processor 的 CPU smoke：原 processor 调用一次、返回相同结果对象、图像/状态/token 值逐项不变 | [实际 processor 包装测试](evidence/actual_processor_wrapper_smoke.jsonl)、[汇总](evidence/summary.json) |
| 历史保护 | 69 NPZ、原推理日志、原 H5 和退出凭据的完整文件 SHA256 前后相同；H5 仍为 record_valid=true、task_success=false、原 episode/finalization ID 不变 | [SHA 和标签](evidence/summary.json) |
| 部署来源保护 | 历史预检列出的 9 份 RPent/RLinf/OpenPI/robosuite 源码与当前文件 SHA256 全部一致 | [部署源码比较](evidence/deployment_source_check.json) |

`audit.json` 含实际任务文本及其 SHA256、原 token 列表、有效 token IDs/mask、有效 decode、丢弃后缀 decode、模型上限、tokenizer 和 processor 文件路径/哈希以及包版本。两个 `effective_processor_input.npz` 保存本轮离线重建的处理后图像、token 和状态，约 128 KB 合计。

## 已执行与采样范围

源记录为 2026-10-27 发布版真实 π0.5 连续 RPC 实验，运行提交 `122c4c03586abdfa7e3117c13e62f8d46f786b04`。本轮只读其已关闭的原文件，用当前实际部署的配置、normalizer、tokenizer 和 processor 进行本地重建；没有加载模型权重、启动 CUDA/模型服务、推理 rollout 或付费调用。

历史服务没有保存内部处理后的语言张量，所以首末语言 token 证据明确标为**离线重建**。源模型输入及推理日志是历史真实输入；处理源码对应旧预检 SHA，原服务的 69 次截断警告与本次重建结果一致。新增的服务只读包装会从今后的真实 processor 调用中直接保存有效张量审计。

当前服务包装保存 `effective_input_audit.jsonl`，按 request index 与原 `inference.jsonl` 对齐；字段包括实际有效 token、mask、文本和 tokenizer hash、图像 shape/dtype/hash、图像 mask，以及审计格式与真实 token 是否一致。

## 复现

使用已有独立模型环境；输出目录必须不存在：

```bash
export LABSIM_POLICY_PYTHON=/path/to/rpent/.venv/bin/python
export LABSIM_PI05_CHECKPOINT=/path/to/RLinf-Pi05-LIBERO-130-fullshot-SFT
export MODEL_RUN=outputs/lab_cuvette_loading/Project_release_v1/pi05_standard_01_model

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
"$LABSIM_POLICY_PYTHON" -m policy_backends.lab_cuvette_env_v1.input_audit \
  --model-path "$LABSIM_PI05_CHECKPOINT" \
  --input-npz "$MODEL_RUN/input_000001.npz" \
  --inference-log "$MODEL_RUN/inference.jsonl" --request-index 1 \
  --output outputs/lab_cuvette_loading/Project_release_v1/input_audit_NEW
```

完整首末请求、69 份 wire hash、H5 分支和原始文件保护检查使用 [audit_evidence.py](audit_evidence.py)：

```bash
OMP_NUM_THREADS=1 "$LABSIM_POLICY_PYTHON" \
  docs/lab_cuvette_loading/Project_release_v1/internal_use/20261028/input_audit/audit_evidence.py \
  --model-path "$LABSIM_PI05_CHECKPOINT" \
  --output outputs/lab_cuvette_loading/Project_release_v1/input_evidence_NEW
```

脚本检查来源模型和环境进程已有退出凭据且本机 PID 已消失。tokenizer 和 normalizer 仅从已有本地文件/cache 读取；缺失时报告具体路径，不下载。首次运行中路径层级错误已在执行任何审计前修复；成功输出使用全新目录，历史文件均未改写。

CPU 自动化测试为 `tests/test_lab_cuvette_pi05_input_audit.py`：原生图像尺寸/字节保持、截断与 mask 核对、真实 processor 输出的审计包装语义、来源证据不一致提前拒绝。与原策略 rollout 契约合计 **13 tests passed**。实际部署 tokenizer/processor 的离线核查单独以上述证据为准，不用假 tokenizer 单元测试代替。
