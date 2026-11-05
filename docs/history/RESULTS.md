# 统一结果索引

本页汇总当前能力依据与历史结果入口，供主页和交接文档统一引用。推荐使用版本仍为 [Project_release_v1](../lab_cuvette_loading/Project_release_v1/README.md)，实际使用从[ONBOARDING](../development/ONBOARDING.md)开始；本页不触发实验、下载或发布。下述结果是各原记录的既有观察，未因本轮文档整理而重新执行。各版本的配置、源码身份、分母、失败和未执行项分别保留，不合并估算新的成功率。

## 发布版与数据资格

- [版本接口与验收导航](../lab_cuvette_loading/Project_release_v1/README.md#验收记录导航)连接普通 Teacher、生命周期、退出/闭合、ACT/DP reader 和真实 RPC 的原始证据。
- [Internal_use_v1 使用验收](../lab_cuvette_loading/Internal_use_v1/20261028/README.md)及[数据用途与移交](../lab_cuvette_loading/Project_release_v1/data_usage.md)分别说明普通示范、诊断、策略评测和资源检查。
- [Size_v1 最终报告与连续视频](../lab_cuvette_loading/Size_v1/results_20261022/LabSim_Size_v1_尺寸变体装载实验报告.md)、[40 集正式审计](../lab_cuvette_loading/Size_v1/data/final40_actual/README.md)：保留 20 成功 / 20 受控失败的历史统计，不能把受控提前结束解释为自然失败分布。

## standard 与固定 Random-10

[Scene_suite_v1 参考运行验证](../lab_cuvette_loading/Scene_suite_v1/README.md#参考运行验证)：2026-11-05/06 新运行，standard 完整成功，Random-10 各一次为 5/10 完整成功；33 次 reset、11 条正式记录闭合/退出及实际 ACT/DP 读取通过。三条抓持漂移、两条碰撞安全失败保持原标签；普通 standard 基线与十一场景分母分别记录。

## Progress 阶段分析

[Progress v1.2 使用入口](../lab_cuvette_loading/Progress_v1_2/README.md)提供在线 `--progress`、已有记录离线分析及便携报告；[实际结果](../lab_cuvette_loading/Progress_v1_2/RESULTS.md)保留当时验证和局限。阶段诊断不修改原 reward、独立评分或数据资格；阶段到达不等于完整任务成功。[Progress v1 历史入口](../lab_cuvette_loading/Progress_v1/README.md)保留旧字段与证据。

## 冻结策略评测与历史恢复

- [Policy_eval_v1 协议与输入审计](../lab_cuvette_loading/Policy_eval_v1/README.md)、[真实逐集结果](../lab_cuvette_loading/Policy_eval_v1/RESULTS.md)：GPT direct P9 与 LIBERO π0.5 按各自冻结协议统计；计划集、已启动集、服务失败、预算终止和未启动集分开记录。
- [Gpt_debug04_v1 身份与独立复测](../lab_cuvette_loading/Gpt_debug04_v1/README.md)、[量化结果](../lab_cuvette_loading/Gpt_debug04_v1/RESULTS.md)：历史原集与新标准场景单集分开，当前完整成功 0/1；有限单集不能推断稳定成功率。它是 v4 工具/context4 的历史策略身份，不等同于 P9。
- [正常策略契约](../lab_cuvette_loading/Project_release_v1/external_policy/contract.md)与[可选部署](../../policy/backends/OPTIONAL_POLICIES.md)定义输入、RPC、动作回执与 tokenizer 等技术细节；接口验证不自动意味着模型完成任务。

## 单细胞资产与 unit

[设备资产与 API](../../demos/cell_assets/README.md)和[单细胞 unit](../../demos/cell_units/README.md)是与比色皿任务并行的扩展。[unit 验证记录](../cell_assets/单细胞Unit验证.md)、[交接汇报](../cell_assets/交接汇报.md)及[代码复核](../cell_assets/代码复核.md)保留当时 expert 成功、policy 失败和缺失设备的不同范围。PCR 孔腔是工程派生模型，限定机械操作不是完整单细胞实验功能或真机校准。

源资产镜像、许可及未发布派生物见[HF 发布与调用指南](../cell_assets/HuggingFace上传指南.md)。原文中的日期分支、机器路径和当时 PR 状态仅作历史身份，不作为当前工作区或发布授权。

## 里程碑与更早记录

- [系列实验历史报告原文](https://github.com/zez2001/LabSim/blob/137f1b20b36f821894b6387ba36ee592231c8b1f/docs/series_20261019/report.md)使用固定基线链接保留原目录与媒体引用；[历史 DOCX 归档及恢复入口](../archive/series_20261019/README.md)记录单文件归档试点的状态、哈希和回取方式。归档清单存在不代表已经发布或允许删除 Git 原件。
- [历史版本索引](README.md)保留 V0、Env、Size 与早期实验的原范围和局限；[背景与规划](../background/README.md)保留研究背景。
- [结果阅读包](../agent_handoff/README.md)区分历史原机配方、工作树草稿、固定提交内容与外部证据；[归档策略](../archive/README.md)记录大文件的回取与保留要求。

## 原始证据与发布状态

历史正文、表格、标签、源路径、媒体和源码指纹保持原字节。Git 中保留必要小证据与运行依赖；大资产/正式数据集的 HF revision 及 Release 包须逐项回读哈希后才称已发布。当前导航不证明远端可用性，也不证明原机忽略输出可由任意检出重建。缺失项按原清单标明，不补造或用派生文件替代原证据。
