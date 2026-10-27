# 发布版安全停止：仅准备，尚未执行

首先检查真实 π0.5 生命周期是否自然触发安全停止。若已有有效新版本安全停止，可直接复用，避免额外碰撞。此脚本没有被执行，只做了离线来源与参数检查。

本目录内的 `envelopes.json` 包含完整 25 条参数，可独立复查。`replay_rpc.py` 是本机严格核查脚本，默认要求 `--repository-root` 下的历史来源文件仍存在且 SHA 一致；这些历史大日志不在本小目录中。脚本使用包内同名计划作为默认输入，`plan_receipt.json` 和 `SHA256SUMS` 记录本轮来源与文件哈希。

## 来源与执行范围

- 来源：已闭合 Project_v1_1 / gpt_debug_05，runtime `58da857e14a0a1152884e13984607a286547a046`。
- 从其 `execution_trace.jsonl` 的 2994 条实际控制记录，按 action_id 提取 25 个原始 public action envelope。
- 保存原 XYZ/rotation、world frame、2 秒持续时间、夹爪目标、力上限；只重绑 episode_id、observation_id、action_id、execution_action_id。
- 六个继承物理执行核心源码与来源提交逐字节相同；计划记录源码与原日志 SHA。发布版增加的 collector/记录/关闭行为单列，不声称整个程序字节相同。
- 每次动作前后记录公开机器人状态、相机元数据和 RGB 原数组 SHA、请求、实际回执、stop/domain。H5 保存配置变换后的图像，native 视频为编码画面；本客户端只记录 native RGB 哈希，不宣称这两者是原 RGB 的逐像素副本。
- 不调用模型、外部收费 API 或预算账本；不改物理、不造标、不绑定器皿、不关闭碰撞。

## 调度命令

仅在真实 π0.5 结束、RPC 8097 保持暂停且 root 允许后运行：

```bash
CUDA_VISIBLE_DEVICES='' /home/wujing/Desktop/vla/labutopia-env/bin/python \
  /tmp/labsim-release-safety-replay-plan-20261027/replay_rpc.py \
  --plan-sha256 82cf00f9ac48ab09ad3bb20ff306984e4cb92ba9be3c0d76c72219bcb15e011e \
  --endpoint http://127.0.0.1:8097 \
  --output /home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/Project_release_v1/safety_replay_rpc_01 \
  --execute
```

省略 `--execute` 只核对离线来源，不连接 RPC、不创建输出目录。

25 条动作的名义仿真时长 50 秒；历史实际停止在 49.9166667 秒，第 25 条仅执行 114/120 控制 tick。按本轮 teacher 1129 秒墙钟 /125.6667 秒仿真的比值，预计约 7.5–10 分钟，属于粗略调度估计。

## 停止与风险

原动作最后导致末端上游 `panda_link6` 接触原仪器盖板 `SourceMesh5`；历史首次禁止接触为 step11978/t49.9083333。此处是历史参考，不据此强制新结果。新版本可能因实际初态、数值响应不同而更早停止或不复现同一碰撞。

初态先检查公开 arm/finger/TCP 与来源是否等价。不等价则不回放，结束为输入条件不匹配。任何预规划拒绝、非预期 target_not_reached、缺少后继观察或 partial execution 均停止，绝不靠新 ID 重发、强压或补动作。请求响应不明时只查询 receipt，不重复运动。最后只做一次相同 ID 的缓存重试，检查时间和状态不变。

脚本结束后保留 RPC 环境运行并暂停，方便 root 后续 reset/短诊断；不关闭或重启 Isaac。

## 原生进程关闭后的审计

1. 将客户端 episode_id 与服务器新增 episode 目录对齐；保存版本、资产 revision、mode、配置与两个来源 SHA。
2. 核对实际执行 tick、仿真时间、首次 contact collider、力/分离与 safety failure_domain；未观察到安全停止时不得写“已复现”。
3. 核对最终 receipt 的 successor observation、终止状态与 final cached retry 零新增步数。
4. H5 complete/publication_state/finalization_id、结果 JSON、完成标记和索引资格一致；gzip footer、未压缩 SHA 与行数全量验证。
5. 侧视/腕视/dual 视频正常关闭、帧数/时戳可读；核对 H5 观测—动作—后继状态。
6. 正常 ACT/DP failure/all_valid 可读、success 应拒绝；post_retreat_window 为 unavailable，撤离后稳定为 null；terminal_window 保持独立语义。
7. 此结果标为确定性历史动作安全诊断，不计入模型新推理、完整装载成功或自然失败概率。

## 其他五项短诊断

薄 CLI 已修复所有原生条件转发。root 提交后从新干净 checkout 在 RPC 关闭、GPU 空闲时执行：

```bash
./labsim demo --project-version Project_release_v1 --record-mode eval \
  --sequence early_finish no_progress unreachable service_timeout user_interrupt \
  --headless \
  --output outputs/lab_cuvette_loading/Project_release_v1/termination_cases_01
```

该命令在本轮只 dry-run 检查，未启动仿真。后两项为明确标记的受控异常注入，不是真实服务断线或用户实际按键。五集同进程，每集先推进真实物理，再调用对应终止路径；所有 H5/视频只在进程真正退出后审计。
