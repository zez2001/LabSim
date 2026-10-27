# 数据用途与移交 CPU 验收（2026-10-28）

当前使用说明见 [Project_release_v1 数据用途、读取与移交](../../../Project_release_v1/data_usage.md)。本目录保存本次工程验证的脚本和小型原始结果，不包含 H5 数据本体。

## 结果

- [真实闭合历史数据验收](summary.json)：π0.5 1 条策略记录 + 10 条资源探针，经旧策展清单明确标注，正式评测索引纳入 1 条、诊断索引显式纳入 11 条；ACT/DP 正常入口读取通过。
- [策略成员及排除清单](policy_only.index.json)：每条记录的用途、来源、纳入状态、排除原因、资格筛选及源文件身份。
- [历史生命周期诊断](lifecycle_diagnostic.index.json)：独立用途 sidecar 下继续保留 `success / failure / all_valid = 2 / 1 / 3`，六个 ACT/DP 实际 batch 读取通过。
- [π0.5 H5 保护](historical_pi05_protection.json)、[生命周期 H5 保护](historical_lifecycle_protection.json)：14 个源 H5 完整 SHA256 和任务标签前后相同，π0.5 SHA256 同时与上一轮记录一致。
- [10 项新增 CPU 用例](cpu_tests_final.xml)：真实小型有效 H5 完成相对目录树移动、缺源文件明确报错、copy 独立移动及相机 hardlink 别名检查；未知用途、明确成员、SHA/身份绑定、活动 writer 和原资格语义均覆盖。
- [集成 CPU 回归](integrated_cpu.xml)：release 生命周期、正式 reader 及本次用途/移交用例。

所有验收均是关闭后的只读 CPU 数据验证；本脚本没有启动 Isaac、模型或付费服务。物理任务及当前版本普通 Teacher 回归由本次发布总报告单独记录。

## 来源与复现

真实运行产物位于 `outputs/lab_cuvette_loading/Internal_use_v1/20261028/data_usage_02`；`data_usage_01` 保留为较早的成功验证。`_02` 对应最终数据用途代码哈希，见 [summary](summary.json)。[完整脚本](audit.py) 可在同一机器保留历史源数据的条件下，指定**新的**输出目录复现：

```bash
python docs/lab_cuvette_loading/Internal_use_v1/20261028/data_usage/audit.py \
  --repo /path/to/LabSim --output /path/to/new-data-usage-audit
```

[证据清单](evidence_manifest.json) 绑定此处每份收据与原输出的路径、大小和 SHA256。这里复制的 `*.index.json` 与 `*_purpose_members.json` 是原始验收收据；其中相对 H5 路径的基准仍是清单声明的原输出位置，并不是本目录。需要实际读取时使用原输出索引，或按当前指南重新建立 sidecar 和索引。原历史 H5、索引和策展清单没有改写。
