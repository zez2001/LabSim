# P8 提示候选 CPU / 离线验证

本轮只实现新 opt-in prompt/client metadata/profile 和旧公共入口三行路由。P7 图像 helper / profile、动作执行、物理、gripper hold、teacher 和 scorer 保持原字节。P8 没有实际 API 或 GPU 结果。

- `change_audit.json`：完整 CPU CI **730 passed / 13 skipped / 0 failed**；14 个保护源码/配置与基准 HEAD 相同。
- `contracts_command.json`、`contracts.xml`、`contracts_stdout.txt`：实际命令及结果，相关源文件运行前后 SHA 相同。
- `git_free_receipt.json`、`git_free_contracts.xml`：无 `.git` 的文件导出内执行 P8+P7 的 **52 个测试**，PATH 中的 git 被拒绝，实际未调用 git。使用精确 58da 基线夹具，兼容测试不依赖本机 Git 历史。
- `closed_P7_instruction_bounds/summary.json` 与 CSV：对真实闭合 GPT06 的原 input_items 不变，只替换 P8 instructions；17 个输入 / 18 个网络尝试，每份增加 993 个序列化字节，最大本地启发式预留 68,805 / 80,000，余量 11,195。6 份完整公开 input_items 独立重建校对旧真实预留；11 份私有项不恢复，只利用旧真实预留中已经计入的大小。
- `cli_dry_run.json`：一集、默认 160 模型调用上限的 stable CLI 计划；无输出目录或仿真创建。

原 P4/P6 冻结夹具比较、P7 direct 与原 public route 比较均保留。新 P8 与 P7 的实际 fake-transport body 只在 instructions 不同；原 CURRENT、图像字节、历史策略、工具 schema/回执保持。新元数据分别记录静态默认 prompt、实际运行 prompt、实际请求 instructions 的 SHA，支持自定义 prompt 时也不会把默认文本冒充实际文本。

P8 只鼓励有当前公开图像依据的、保守可逆局部观察动作；没有自动探索、方向/距离/安全高度/路径、环境真值或专家宏。没有有依据的安全动作或出现异常时，仍停止且不释放。CPU 和旧样本反事实预算不是新任务成绩，也不保证未来回复总能低于原上限。
