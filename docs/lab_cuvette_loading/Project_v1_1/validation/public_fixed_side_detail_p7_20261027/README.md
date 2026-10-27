# P7 最终 CPU / 离线准备证据

**最终范围只取 `release/`。** 同目录其他 `contracts*`、`context2_*` 和 `exploratory_*` 是开发中候选的保留记录；其中有早期双历史 / 5 图 / 极薄预算余量版本，不代表最终 profile。

最终 P7 为：固定侧视 ROI → 480×480 派生图；原 CURRENT side+wrist 保留；最多一张历史腕视（优先首次公开双侧接触，参考未建立时才上一不同观测，CURRENT 参考不重复）；context2 保留最近一个完整工具回合。P6 双历史 / context4 profile 与 helper 保持原 SHA。所有原动作、物理、判分及预算限额保持。

- [最终改动与来源保护审计](release/change_audit.json)：717 passed / 13 skipped / 0 failed，按仓库 CPU CI 入口执行。39 个 P7 专用测试包含公共 old runner → P7 的 fake transport 路由和原 P4/P6 对冻结 58da 的实际 fake-payload 一致性。
- [精确测试命令及前后源 SHA](release/contracts_command.json)、[JUnit](release/contracts.xml)、[stdout](release/contracts_stdout.txt)。源码在该次运行期间未变化。
- [25 个闭合公开前缀的预算范围](release/closed_context_bounds/summary.json)、[逐决策表](release/closed_context_bounds/bounds.csv)、[原真实预留的相关行](release/closed_context_bounds/source_reservation_evidence.json)。公开占位最大 63,462；把旧真实预留约束的全部私有项字节保守分配给保留回合后，上界 67,829，距原 80,000 限额 12,171。没有读取或复原私有 reasoning 内容；未知大小范围不等于真实新请求或 tokenizer 结果。
- [最终 D24 脱机图像预览](../../camera/fixed_side_detail_P7_D24_preview/README.md)：4 张图、原 CURRENT 五内容块最后、完整 source/derived SHA、像素中心 A/K，标准库验证通过。来源进程已真实闭合并匹配同一个 run；输出拒绝写入原 closed run 的任何位置。相同 CI Python/Pillow12.3 重放字节一致；跨编码库版本不承诺派生 JPEG 字节一致。

本轮 API=0、GPU=0、动作=0，不产生 P7 任务成功/失败。它是候选准备与接口验证，真实模型观察及任务实验仍需另行执行。不能以固定放大图宣称新像素细节、物理精度或已经解决碰撞。

复算（会拒绝覆盖输出目录）：

```bash
python docs/lab_cuvette_loading/Project_v1_1/validation/public_fixed_side_detail_p7_20261027/audit_context2_bounds.py \
  --repo . \
  --source outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000/gpt_control \
  --ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output /tmp/p7-new-bound-audit
```

`audit_context2_bounds.py` 是可复核的 CPU 分析源，相关测试会导入它检查私有字节残差范围算法，因此与新模块/profile/tests 一起纳入提交。`release/` 内的绝对原路径仅说明出处，阅读包不承诺附带原 H5 或完整原会话。新 profile 名为 `cubence_gpt6_context2_640high_temporal_detail.json`；未提交的旧误名 profile 已更正，没有真实运行需要迁移。
