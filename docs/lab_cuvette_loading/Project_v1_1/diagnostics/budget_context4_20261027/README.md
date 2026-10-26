# 独立 4 上下文候选配置

新增 `config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4.json`。它从默认 `cubence_gpt6.json` 只替换一处字节：`max_context_messages` 由 12 改为 4。其他所有字节保持一致，包括 gpt-6-astra、512×384/low、输出限制、超时、$30/1500 次上限及定价。默认 provider 配置保持不变，没有调用 API 或修改共享账本。

## 结构检查

实际 `run_episode` 在明确 synthetic client/environment/tools 下完成 9 个纯 CPU 决策：4 上下文保留最近 **2 个完整工具回合**。每组 function_call、匹配 call_id 的 output 和同组 reasoning item 保持完整，当前 Task 文本、public task_language、A1/目标座 ID、双相机标定和当前双图每步仍发送。没有读取模型私有 reasoning。结果见 `context_structure_CPU.json`，不代表服务端接受或闭环策略质量。

相对 12 的最近 6 回合，4 的记忆窗口明显缩短。旧操作的回执被遗忘可能改变策略、所需步数及重试率，不能只凭结构检查断言策略能力等同。

## 预算投影与门槛

按前一 GPT02 的 33 个实际已结算请求拟合，4 上下文稳态预计约 **$0.071424/决策**，完整一条若用 40/50/60 决策，分别约 **$2.82/$3.54/$4.25**。这些均为投影，尚无实际 4 上下文费用；不假设缓存优惠，实际输出/动作数/重试变化尚未知。

余额快照为 **$19.363338**。若一次完整成功 debug 和正式5条都在 40 决策附近，总投影约 **$16.93**，剩约 **$2.43**；在这些假设下有希望保留 $2 缓冲。若各需 50–60 决策则仍不足。`cost_projection.json` 保存不同 debug/正式长度的 9 组投影，不能把其中“可覆盖”当成正式放行。

**下一步先显式采用本配置运行完整 debug。只有该配置取得独立判分确认的真实完整装载成功，并复核实际费用后，才能考虑冻结和正式5次。** 短 CPU/API 诊断不能满足这个门槛；旧预算说明中“短诊断直接 formal”的建议已明确撤回。

调用示例（本轮没有执行）：

```bash
./labsim eval --project-version Project_v1_1 --backend gpt6 --episodes 1 \
  --provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4.json \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_context4_debug_NEW
```

输出目录必须为新目录。后续仍使用原共享账本，保留全部历史 timeout 预留；不提高授权上限、不重置账本、不把预算停止或短诊断标成完整成功。
