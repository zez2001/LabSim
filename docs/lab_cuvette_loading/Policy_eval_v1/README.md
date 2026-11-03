# 器皿装载冻结策略评测

本目录提供 GPT-6 Astra direct P9 与 `RLinf-Pi05-LIBERO-130-fullshot-SFT` RPC 方案的冻结协议、输入审计、真实运行证据和可重复统计。任务为 `lab_cuvette_loading / Project_release_v1 / standard`，使用 Progress v1.2。两组保留原生适配器；任务判分、资产、物理、动作转换和 reward 沿用发布基线。

本轮结果见 [RESULTS.md](RESULTS.md)。模型及输入事实见 [GPT 身份](gpt_identity.json)、[GPT 输入与工具](input_contracts.md)、[π0.5 身份](pi05_identity.json)及[π0.5 输入契约](pi05_input_contract.md)。原始大型 H5 与模型输入留在工程输出目录，反馈包保存其身份、SHA256 和闭合核验结果。

## 协议与预算

[冻结协议](../../../config/lab_cuvette_loading/Policy_eval_v1/protocol.json)记录运行源码、锁定依赖、场景指纹、资产和相机、170 秒仿真上限、安全要求、每组原生调用限制及顺序。[trial 清单](../../../config/lab_cuvette_loading/Policy_eval_v1/trial_plan.json)预列每组 10 集。正式记录用途为 `policy_evaluation`；短接口检查为 `lifecycle_diagnostic`，分别统计。

共同费用账本保留历史累计调用，不重新创建以绕过额度。开始前累计 333 次网络请求、估算 USD 27.8942；硬上限 USD 30 / 1500 次。费用根据返回 usage 和冻结配置费率估算，实际供应商账单及账户倍率未知。预算终止、服务失败及策略失败都保留在已启动集主表；未启动集单列。

## 运行单集

精确复现实验使用协议声明的源码提交和独立干净 checkout。机器路径在原协议中作为运行身份保留；迁移机器时建立另一个命名协议，重新核对环境与输入，保留原协议。

```bash
git worktree add --detach /absolute/path/to/clean-runtime 3ca253324b1ec540ae5ec07f2110c9c091f6ddd1
"$LABSIM_PYTHON" scripts/run_lab_cuvette_policy_eval.py \
  --protocol config/lab_cuvette_loading/Policy_eval_v1/protocol.json \
  --checkout /absolute/path/to/clean-runtime --group gpt6 --phase formal \
  --trial-id gpt6_01 --output /absolute/path/to/new_gpt6_run
```

π0.5 用同一个命令，将 `--group`、`--trial-id` 和输出目录分别设为 `pi05`、`pi05_01` 和新目录。封装依次启动原发布版 RPC、原 checkpoint 服务及原 transfer 客户端，并关闭全部进程。GPU 顺序运行，不在 GPT 试验中驻留 π0.5 模型。

封装显式指定 `--episodes 1`；旧 `eval` 的兼容默认值为 5。GPT 凭据从用户私有的 `~/.local/share/labsim/credentials/cubence.key` 读入子进程内存，文件须仅所有者可读。命令、协议、日志、报告及提交均不保存凭据。原费用硬上限仍会阻止超额复现调用。

预检使用独立输出和 `--phase diagnostic`，仅验证实际模型输入、动作、回执、暂停时序、记录和退出。正式模式要求协议标记为已冻结、预检通过。`--check-only` 可检查版本和源码哈希，不启动模型或仿真。

## 闭合核验与统计

所有输出使用新路径。等待本集原生进程退出后执行：

```bash
"$LABSIM_PYTHON" docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_episode.py \
  /absolute/path/to/run/environment/episode_0000 \
  --expected-purpose policy_evaluation --output /absolute/path/to/new_closed_receipt.json

"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.analysis \
  /absolute/path/to/trials.json --output /absolute/path/to/new_analysis
"$LABSIM_PYTHON" -m demos.lab_cuvette_policy_eval_v1.plots \
  /absolute/path/to/new_analysis/summary.json --manifest /absolute/path/to/trials.json \
  --output /absolute/path/to/new_figures
```

[汇总模块说明](../../../demos/lab_cuvette_policy_eval_v1/README.md)定义 trial 成员、用途、成本摘要和所有分母。完整事件流包含 finalize 事件；原判分决定完整任务结果，Progress v1.2 提供阶段和有效连续量。没有到达入口区域时，装载误差为 `not_reached / N/A`；未建立抓持参考时，漂移为 N/A。跨集统计先逐集归约，再等权汇总。

核验同时保留任务结果、环境有效性、记录完整性和数据资格。闭合通过可以对应任务失败；几何预检阻塞、启动失败和服务异常分别记录。历史 Teacher、π0.5 及 held 未完成记录只用于方法核验，不进入本轮正式分母。

## 结果移交

工程反馈包提供协议、源码/配置身份、逐集 CSV/JSON、完整逐步 Progress、事件、HTML、代表录像、输入摘要和核验凭据。汇报包提供中文 DOCX 及其实际引用的视频。两包均保留 SHA256 清单；大型 H5、模型权重和原始详细日志留在工程端。
