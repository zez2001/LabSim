# P8：仅提示的主动观察候选

P7 的 GPT06 已实际完成抓取及离架，随后在未装载时主动结束。公开侧视/detail 有整手与盖板的相对轮廓，腕视仍主要看见持物和架体；这些图像没有直接建立到内部座的完整三维路径。它是 `TASK_INCOMPLETE`，不是碰撞、完整搬运或装载成功。

P8 只追加一个通用澄清：对整条路线不确定，不等于不存在可由当前图像支持的局部安全观察动作。模型可以在现有工具限制内，选择保守、可逆的平移或旋转来产生不同视角，随后重新检查图像和触觉；原地 `observe` 不改变机位，重复盲目抬升也不是路线证据。没有有依据的局部安全动作，或出现实际安全停止/异常时，仍须停止且不释放。它不提供方向、距离、高度、目标坐标、路径、动作数或教师阶段，也不强制模型进行探索。

P8 保留 P7 的 side v3 / wrist v2、固定 ROI、480×480 detail、当前双图、最多一张历史腕视、context2、五个通用工具、执行器与判分。P7 源码 SHA `4f1b481f…`、profile SHA `559e5fdd…` 保持；旧入口只增加显式 `active_view_control` 路由。新 client 只有配置校验，新 Tools 只增加版本/提示哈希等元数据，没有覆盖任何动作、观测、限幅或停止函数。

新入口：

```bash
./labsim eval --project-version Project_v1_1 --backend gpt6 --episodes 1 --max-calls 160 \
  --provider-config config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view.json \
  --budget-ledger outputs/lab_cuvette_loading/Project_v1/cubence_budget.json \
  --output outputs/lab_cuvette_loading/Project_v1_1/gpt_P8_NEW --dry-run
```

原生运行参数与现有 GPT 入口一致，独立 profile 为：

```text
config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view.json
```

可继续通过 `python -m demos.lab_cuvette_project_v1_1.run --backend gpt6 --episodes 1 --headless --provider-config <上述profile> --budget-ledger <原共享ledger> --output <新目录>` 调用。凭据仍仅由进程环境注入，不写入配置或命令。默认 `max_calls=160`；$30 / 1500 请求、80k 本地输入启发式、1024 输出、原 timeout / retry / reasoning effort 均保留，不新增 formal 或训练流程。

在**已闭合 GPT06 的原输入不变**这个反事实条件下，只替换 instruction 文本会增加 993 个序列化字节；17 个公开输入 / 18 次网络尝试的最大原客户端预留变为 68,805，距 80k 为 11,195。6 份无私有项的完整 input_items 已独立重建并核对原真实预留；另 11 份不恢复私有项，只利用旧真实预留已经计入其大小这一事实。未来 P8 会话可能产生不同回复，仍会在网络前接受原限额检查。该结果不是实际 tokenizer、计费或 P8 效果证明。

证据：[闭合 P7 的 instruction 预算审计](validation/public_active_view_p8_20261027/closed_P7_instruction_bounds/summary.json)。CPU 测试覆盖公共入口→P8、实际 fake-transport prompt/hash、与 P7 除 instructions 外的整份 body 相同、原 P7 路由不变、P4/P6 冻结夹具回归、无 Git 历史导出运行。

本交付阶段没有执行 P8 API 或 GPU，不能将提示候选写成已完成任务。安全可行性与真实进展须由下一条独立、连续、完整记录验证。
