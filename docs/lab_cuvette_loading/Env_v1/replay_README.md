# Env_v1 物理动作回放

正式入口为 `main.py --config-name lab_cuvette_env_v1 --env-mode replay`。该入口重新启动同一个 Env_v1 环境，将关闭并完成记录的 episode 中每个控制周期的实际关节位置目标、夹爪目标及作用力限制作为正常类型化动作下发。它不调用教师或模型，不设置器皿位姿，不跳过几何门控；结束后重新独立判分，不继承源轨迹的成功标签。

## 已实际执行的命令

在工程根目录运行；以下输出目录已存在，重试时请换用新的目录名。

```bash
OMNI_KIT_ACCEPT_EULA=YES ../labutopia-env/bin/python -u main.py \
  --config-name lab_cuvette_env_v1 \
  --env-mode replay \
  --replay-episode outputs/lab_cuvette_loading/Env_v1/rpc_01/episode_0003 \
  --replay-max-ticks 15 \
  --replay-zero-delay \
  --headless \
  --output outputs/lab_cuvette_loading/Env_v1/replay_astra03_01
```

这是 Astra 第三次实际接口尝试的 **15 个控制周期、0.25 秒短诊断回放**，不是完整装载任务或新一次模型推理。进程实际退出码为 0；包含初始化、几何审计、回放和清理的墙钟耗时为 68.40 秒，不能用作单独的回放性能测量。图形界面运行可去掉 `--headless`，本轮实际验证采用上述无界面命令。省略 `--replay-max-ticks` 将回放源记录的全部控制周期；当前短源记录本身也只有 15 个周期。

15/15 个控制周期已执行。源命令与实际下发命令的最大差分别为机械臂 0 rad、手指 0 m，作用力限制差为 0 N。这里只验证这一段的命令一致性，不声明任意轨迹或完整物理状态逐位可重复。新的独立结果为 `record_valid=true`、`task_success=false`、`TASK_INCOMPLETE / REPLAY_SOURCE_EXHAUSTED`，完整装载资格保持 false；原始 false 标签只作为来源证据保留。

## 输入契约和覆盖规则

- 输入目录必须含完整关闭、身份一致的 `config.yaml`、`result.json` 和 Env_v1 HDF5。校验精确 schema、动作含义、控制周期、时间连续性、辅助命令可用性和有限数值；拒绝外部/软链接、虚拟或外部数据存储。
- 当前支持 60 Hz 控制及整数物理步比例；部分控制周期或无法按 60 Hz 还原的记录会被拒绝。读取完整 `control_auxiliary/command_q` 九维目标，前七维为 rad、两手指为 m，不将旧八维训练表示误作完整物理命令。
- 源配置是物理场景、布局、seed、时序和动作的权威；与 CLI 冲突的配置不用于重新定义源场景，并在清单中记录。随机布局只逆转已记录的实际组装平移一次，再用原 seed/options 恢复；缺少所需元数据会明确报错。该随机恢复规则已有 CPU 契约测试，本轮实际回放源为标准布局。
- 默认启用 `--replay-zero-delay`：源 Astra03 配置早于已验证的渲染同步修复，因此只对当前运行启用 Hydra 完成等待顺序。该覆盖明确写入 `replay_source.json.runtime_overrides`，不改物理步长、控制周期、动作、FPS、布局或源文件。`--no-replay-zero-delay` 可关闭此显式覆盖。
- 若正常动作边界产生限幅，源命令和实际下发命令分别保留。混合 rad/m 的旧数值最大差不是物理范数；另存机械臂 rad 与手指 m 的最大差。
- 原始阶段通过 `actions_raw_json.source_phase` 保存；回放观测第一帧仍为 `RESET`，后续为 `REPLAY`，不能用这些标记冒充已经完成提取、插入或释放。

## 证据与产物

[实际结果摘要](data/replay_astra03_01_actual_summary.json)、[实际进程退出证据](runtime/replay_astra03_01_process.json)、[8 项 CPU 契约检查](data/replay_cpu_contract_validation.json) 已保存。独立只读检查见 [数据与视频核查](data/replay_astra03_01_inspection/inspection.json) 和 [渲染姿态核查](data/replay_astra03_01_inspection/renderer_USD_sync_audit.json)：普通 ACT/DP 加载、15 行动作及后继时间、两路各 15 个有效唯一传感器帧和四路视频完整解码通过；腕相机 15/15 帧渲染位姿匹配当前 USD。源与新 HDF5 的检查前后哈希不变。

本机原始产物位于 `outputs/lab_cuvette_loading/Env_v1/replay_astra03_01/`，含 `replay_source.json`、`replay_commands.jsonl`、`replay_result.json` 和新 `episode_0000` 的完整 HDF5、双视角及近景视频、接触记录和独立评分。原始 Astra 源配置、HDF5 与结果文件的 SHA256 均保持不变。大体积原始输出不加入精简阅读包，也不依赖其存在来声称完整装载成功。

当前已验证范围是正式入口、短动作物理回放、记录闭环和独立重新判分。原座几何门控仍有效；完整装载回放、长轨迹和随机轨迹的实际回放尚未验证。
